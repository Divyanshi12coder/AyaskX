"""api/services/recovery_service.py — adapter over SelfHealingOrchestrator."""

from __future__ import annotations

from typing import Any


class RecoveryService:
    def __init__(self, execution_store, orchestrator) -> None:
        self._store = execution_store
        self._orch = orchestrator

    def get_fault(self, execution_id: str) -> dict[str, Any] | None:
        rec = self._store.get(execution_id)
        return rec.get("fault_report") if rec else None

    def get_localization(self, execution_id: str) -> dict[str, Any] | None:
        rec = self._store.get(execution_id)
        return rec.get("fault_localization") if rec else None

    def get_root_cause(self, execution_id: str) -> dict[str, Any] | None:
        rec = self._store.get(execution_id)
        return rec.get("root_cause") if rec else None

    def get_recovery_decision(self, execution_id: str) -> dict[str, Any] | None:
        rec = self._store.get(execution_id)
        return rec.get("recovery_decision") if rec else None

    def get_repair_plan(self, execution_id: str) -> dict[str, Any] | None:
        rec = self._store.get(execution_id)
        return rec.get("repair_plan") if rec else None

    def get_recovery_result(self, execution_id: str) -> dict[str, Any] | None:
        rec = self._store.get(execution_id)
        return rec.get("recovery_result") if rec else None

    def get_self_healing(self, execution_id: str) -> dict[str, Any] | None:
        rec = self._store.get(execution_id)
        return rec.get("self_healing") if rec else None

    def trigger_self_healing(
        self,
        execution_id: str,
        *,
        auto_approve_low_risk: bool = False,
    ) -> dict[str, Any]:
        """
        Trigger the full self-healing chain on a stored execution record.

        Safety invariants are preserved:
        - MANUAL_REVIEW and QUARANTINE decisions are never auto-executed.
        - Only LOW-risk plans without MANUAL_REVIEW steps may be auto-approved
          when auto_approve_low_risk=True.
        """
        rec = self._store.get(execution_id)
        if not rec:
            return {"error": f"Execution '{execution_id}' not found."}

        # Reconstruct minimal PipelineExecution from stored record
        from core.pipeline.executor import PipelineExecution, NodeExecution
        from core.pipeline.status import PipelineStatus, NodeStatus
        from datetime import datetime, timezone

        def _parse_dt(s: str | None):
            if not s:
                return datetime.now(timezone.utc)
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return datetime.now(timezone.utc)

        nodes = []
        for n in rec.get("nodes", []):
            try:
                st = NodeStatus[n["status"].upper()] if n.get("status") else NodeStatus.UNKNOWN
            except Exception:
                st = NodeStatus.UNKNOWN
            nodes.append(NodeExecution(
                execution_id=execution_id,
                node_id=n.get("node_id", "unknown"),
                status=st,
                started_at=_parse_dt(n.get("started_at")),
                finished_at=_parse_dt(n.get("finished_at")),
                error_type=n.get("error_type"),
                error_message=n.get("error_message"),
                checkpoint_id=n.get("checkpoint_id"),
                output_metadata=n.get("output_metadata", {}),
            ))

        status_str = rec.get("status", "failed")
        try:
            pl_status = PipelineStatus[status_str.upper()]
        except Exception:
            pl_status = PipelineStatus.FAILED

        pipeline_execution = PipelineExecution(
            execution_id=execution_id,
            status=pl_status,
            nodes=tuple(nodes),
            started_at=_parse_dt(rec.get("started_at")),
            finished_at=_parse_dt(rec.get("completed_at")),
        )

        from core.self_healing.orchestrator import SelfHealingOrchestrator
        healer = SelfHealingOrchestrator(
            checkpoint_manager=self._orch.checkpoint_manager,
            auto_approve_low_risk=auto_approve_low_risk,
            pipeline_id=execution_id,
        )
        result = healer.handle_failure(pipeline_execution)
        result_dict = result.to_dict()

        # Persist
        self._store.update(execution_id, {
            "self_healing": result_dict,
            "fault_report": result_dict.get("fault_report"),
            "fault_localization": result_dict.get("localization"),
            "root_cause": result_dict.get("root_cause"),
            "recovery_decision": result_dict.get("recovery_decision"),
            "repair_plan": result_dict.get("repair_plan"),
            "recovery_result": result_dict.get("recovery_result"),
            "status": self._map_sh_status(result_dict.get("final_status", "")),
        })
        return result_dict

    @staticmethod
    def _map_sh_status(sh_status: str) -> str:
        mapping = {
            "resumed": "succeeded",
            "rolled_back": "rolled_back",
            "manual_review": "escalated",
            "quarantined": "escalated",
            "aborted": "aborted",
            "failed": "failed",
            "no_fault": "succeeded",
        }
        return mapping.get(sh_status.lower(), "recovering")
