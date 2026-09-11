"""
api/services/pipeline_service.py
----------------------------------
Thin adapter: runs AyaskXOrchestrator in a background thread so the
HTTP request returns immediately with execution_id + status=queued.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineService:
    def __init__(self, orchestrator, execution_store) -> None:
        self._orch = orchestrator
        self._store = execution_store

    # -----------------------------------------------------------------------
    # Start (non-blocking)
    # -----------------------------------------------------------------------

    def start_run(
        self,
        df: pd.DataFrame,
        *,
        dataset_id: str,
        dataset_path: str,
        target: str | None = None,
        task_type: str | None = None,
        max_candidates: int | None = None,
    ) -> str:
        """
        Submit a pipeline run.  Returns execution_id immediately.
        Actual execution runs in a daemon thread.
        """
        import uuid
        execution_id = str(uuid.uuid4())

        # Initial record
        self._store.save(execution_id, {
            "execution_id": execution_id,
            "dataset_id": dataset_id,
            "dataset_path": dataset_path,
            "status": "queued",
            "created_at": _utc_now(),
            "started_at": None,
            "completed_at": None,
            "success": None,
            "message": "",
            "warnings": [],
        })

        t = threading.Thread(
            target=self._run_in_background,
            args=(execution_id, df, dataset_path, target, task_type, max_candidates),
            daemon=True,
            name=f"ayaskx-pipeline-{execution_id[:8]}",
        )
        t.start()
        return execution_id

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        return self._store.get(execution_id)

    def list_executions(self) -> list[dict[str, Any]]:
        return self._store.list_all()

    def get_status(self, execution_id: str) -> str | None:
        rec = self._store.get(execution_id)
        return rec.get("status") if rec else None

    def get_nodes(self, execution_id: str) -> list[dict[str, Any]]:
        rec = self._store.get(execution_id)
        if not rec:
            return []
        return rec.get("nodes", [])

    def get_node(self, execution_id: str, node_id: str) -> dict[str, Any] | None:
        nodes = self.get_nodes(execution_id)
        for n in nodes:
            if n.get("node_id") == node_id:
                return n
        return None

    def get_checkpoints(self, execution_id: str) -> list[dict[str, Any]]:
        rec = self._store.get(execution_id)
        if not rec:
            return []
        return rec.get("checkpoints", [])

    def get_checkpoint(self, execution_id: str, checkpoint_id: str) -> dict[str, Any] | None:
        for c in self.get_checkpoints(execution_id):
            if c.get("checkpoint_id") == checkpoint_id:
                return c
        return None

    # -----------------------------------------------------------------------
    # Background runner
    # -----------------------------------------------------------------------

    def _run_in_background(
        self,
        execution_id: str,
        df: pd.DataFrame,
        dataset_path: str,
        target: str | None,
        task_type: str | None,
        max_candidates: int | None,
    ) -> None:
        self._store.update(execution_id, {
            "status": "running",
            "started_at": _utc_now(),
        })
        try:
            result = self._orch.run(
                df,
                execution_id=execution_id,
                dataset_path=dataset_path,
                target=target,
                task_type=task_type,
                max_candidates=max_candidates,
                save_artifact=True,
            )
            summary = result.to_summary()
            status = "succeeded" if result.success else "failed"

            # Collect checkpoint metadata from the checkpoint manager
            ckpt_mgr = self._orch.checkpoint_manager
            ckpts = self._extract_checkpoints(ckpt_mgr, execution_id)

            # Collect pipeline execution node records
            pe = result.pipeline_execution
            nodes = self._extract_nodes(pe)

            self._store.update(execution_id, {
                "status": status,
                "completed_at": _utc_now(),
                "success": result.success,
                "message": summary.get("message", ""),
                "warnings": summary.get("warnings", []),
                "summary": summary,
                "nodes": nodes,
                "checkpoints": ckpts,
                # stage results as dicts
                "task_type": summary.get("task_type"),
                "target": summary.get("target"),
                "best_model": summary.get("best_model"),
                "best_score": summary.get("best_score"),
                "validation_strategy": summary.get("validation_strategy"),
                "candidates": summary.get("candidates", []),
                # raw result objects serialized
                "characterization": self._safe_to_dict(result.characterization),
                "feature_roles": self._safe_to_dict(result.feature_roles),
                "leakage_report": self._safe_to_dict(result.leakage_report),
                "preprocessing_plan": self._safe_to_dict(result.preprocessing_plan),
                "candidate_report": self._safe_to_dict(result.candidate_report),
                "training_result": self._safe_to_dict(result.training_result),
                "validation_strategy_detail": self._safe_to_dict(result.validation_strategy),
            })
        except Exception as exc:
            self._store.update(execution_id, {
                "status": "failed",
                "completed_at": _utc_now(),
                "success": False,
                "message": f"Pipeline raised exception: {type(exc).__name__}: {exc}",
            })

    @staticmethod
    def _safe_to_dict(obj: Any) -> Any:
        if obj is None:
            return None
        if hasattr(obj, "to_dict"):
            try:
                return obj.to_dict()
            except Exception:
                pass
        if hasattr(obj, "__dict__"):
            try:
                import json
                return json.loads(json.dumps(vars(obj), default=str))
            except Exception:
                pass
        return str(obj)

    @staticmethod
    def _extract_nodes(pe: Any) -> list[dict[str, Any]]:
        if pe is None:
            return []
        nodes = getattr(pe, "nodes", ())
        out = []
        for n in nodes:
            out.append({
                "node_id": getattr(n, "node_id", None),
                # Persist the wire value rather than Enum.__str__ (for
                # example, "failed", not "NodeStatus.FAILED").  The latter
                # cannot be reconstructed reliably by the recovery API.
                "status": getattr(getattr(n, "status", None), "value", getattr(n, "status", "")),
                "started_at": str(getattr(n, "started_at", "")),
                "finished_at": str(getattr(n, "finished_at", "")),
                "error_type": getattr(n, "error_type", None),
                "error_message": getattr(n, "error_message", None),
                "checkpoint_id": getattr(n, "checkpoint_id", None),
                "output_metadata": getattr(n, "output_metadata", {}),
            })
        return out

    @staticmethod
    def _extract_checkpoints(ckpt_mgr: Any, execution_id: str) -> list[dict[str, Any]]:
        if ckpt_mgr is None:
            return []
        try:
            all_ckpts = ckpt_mgr.list()
            out = []
            for ckpt in all_ckpts:
                if getattr(ckpt, "execution_id", None) == execution_id:
                    out.append({
                        "checkpoint_id": ckpt.checkpoint_id,
                        "execution_id": ckpt.execution_id,
                        "node_id": ckpt.node_id,
                        "created_at": str(ckpt.created_at),
                        "validation_status": ckpt.validation_status,
                        "artifact_path": ckpt.artifact_path,
                        "data_hash": ckpt.data_hash,
                    })
            return out
        except Exception:
            return []
