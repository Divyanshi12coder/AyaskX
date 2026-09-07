"""
core/platform/orchestrator.py
------------------------------
AyaskX Core Platform Orchestrator.

Phases B + C: PIPELINE UNIFICATION + EXECUTION ENGINE

The AyaskXOrchestrator is the single coherent entry point to the
AyaskX intelligent ML pipeline.

It connects all existing modules into a deterministic, end-to-end
executable pipeline:

  DatasetDiscovery
      ↓
  DatasetCharacterizer
      ↓
  TaskDetector
      ↓
  FeatureRoleDetector
      ↓
  LeakageDetector
      ↓
  PreprocessingRecommender
      ↓
  ValidationStrategySelector
      ↓
  ModelCandidateGenerator
      ↓
  ModelTrainer (train + evaluate)
      ↓
  ModelArtifact (best model, stored for inference)
      ↓
  InferenceEngine

Self-healing layer (available via analyze_and_heal()):
  FaultDetector → FaultLocalizer → RootCauseAnalyzer
      → RecoveryDecisionEngine → RecoveryExecutor
      → RepairPlanner → SandboxExecutor

Monitoring:
  PipelineMonitor (alerts after each stage)

Design principles:
- Reuses ALL existing modules. Zero duplication of logic.
- Does NOT modify any existing API.
- Pipeline is additive: caller can run full pipeline OR individual stages.
- Dataset adaptivity: task type, preprocessing, and validation strategy
  are inferred automatically — never hardcoded.
- Every stage produces structured, immutable results.
- Checkpoints are created at key stages.
- All outputs are tracked and retrievable.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _df_fingerprint(df: pd.DataFrame) -> str:
    """Deterministic fingerprint of a DataFrame's structure and content hash."""
    shape_part = f"{df.shape[0]}x{df.shape[1]}"
    cols_part = ",".join(sorted(df.columns.tolist()))
    try:
        # Sample-based hash for speed
        sample = df.sample(min(100, len(df)), random_state=42) if len(df) >= 2 else df
        content_part = hashlib.md5(
            pd.util.hash_pandas_object(sample, index=True).values.tobytes()
        ).hexdigest()[:16]
    except Exception:
        content_part = "nohash"
    return f"sha:{shape_part}:{content_part}"


# ---------------------------------------------------------------------------
# OrchestratorResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrchestratorResult:
    """
    Immutable top-level result of AyaskXOrchestrator.run().

    Contains references to all stage results for downstream use.
    """

    execution_id: str
    dataset_path: str
    dataset_fingerprint: str

    # Stage outputs
    characterization: Any = None        # DatasetCharacterization
    task_detection: Any = None          # TaskDetectionResult
    feature_roles: Any = None           # FeatureRoleReport
    leakage_report: Any = None          # LeakageReport
    preprocessing_plan: Any = None      # PreprocessingPlan
    validation_strategy: Any = None     # ValidationStrategy
    candidate_report: Any = None        # ModelCandidateReport
    training_result: Any = None         # TrainingResult
    model_artifact: Any = None          # ModelArtifact

    # Self-healing outputs
    fault_report: Any = None            # FaultReport
    fault_localization: Any = None      # FaultLocalization
    root_cause_report: Any = None       # RootCauseReport
    recovery_decision: Any = None       # RecoveryDecision
    recovery_result: Any = None         # RecoveryResult
    repair_plan: Any = None             # RepairPlan

    # Execution
    pipeline_execution: Any = None      # PipelineExecution
    success: bool = False
    message: str = ""
    warnings: tuple[str, ...] = ()
    alerts: tuple[Any, ...] = ()

    started_at: datetime = field(
        default_factory=_utc_now
    )
    completed_at: datetime | None = None

    def to_summary(self) -> dict[str, Any]:
        """Return a JSON-serializable summary."""
        td = self.task_detection
        vs = self.validation_strategy
        tr = self.training_result
        cr = self.candidate_report

        return {
            "execution_id": self.execution_id,
            "dataset_path": self.dataset_path,
            "dataset_fingerprint": self.dataset_fingerprint,
            "success": self.success,
            "message": self.message,
            "task_type": getattr(td, "task_type", None),
            "target": getattr(td, "target", None),
            "validation_strategy": getattr(vs, "strategy", None),
            "candidates": [
                c.name for c in getattr(cr, "candidates", [])
            ],
            "best_model": getattr(tr, "best_model_name", None),
            "best_score": getattr(tr, "best_score", None),
            "warnings": list(self.warnings),
            "alerts": len(self.alerts),
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at else None
            ),
        }


# ---------------------------------------------------------------------------
# AyaskXOrchestrator
# ---------------------------------------------------------------------------


class AyaskXOrchestrator:
    """
    AyaskX Core Platform Orchestrator.

    Connects all existing AyaskX modules into a coherent, end-to-end
    intelligent ML pipeline with self-healing, checkpointing, monitoring,
    and inference support.

    Usage
    -----
    orchestrator = AyaskXOrchestrator()
    result = orchestrator.run(df, dataset_path="data/train.csv")

    All parameters are optional — the orchestrator infers task type,
    preprocessing strategy, and validation strategy from the data.
    """

    def __init__(
        self,
        checkpoint_root: str | Path = ".ayask_checkpoints",
        artifact_root: str | Path = ".ayask_artifacts",
    ) -> None:

        # ── Existing modules ─────────────────────────────────────────────────
        from core.datasets.characterization.characterizer import DatasetCharacterizer
        from core.task_detection.detector import TaskDetector
        from core.feature_roles.detector import FeatureRoleDetector
        from core.leakage.detector import LeakageDetector
        from core.preprocessing.recommender import PreprocessingRecommender
        from core.validation.strategy import ValidationStrategySelector
        from core.models.candidates import ModelCandidateGenerator
        from core.models.trainer import ModelTrainer

        # ── New modules ──────────────────────────────────────────────────────
        from core.pipeline.executor import PipelineExecutor
        from core.pipeline.checkpoints.manager import CheckpointManager
        from core.fault.detector import FaultDetector
        from core.fault.localizer import FaultLocalizer
        from core.recovery.decision import RecoveryDecisionEngine
        from core.recovery.executor import RecoveryExecutor
        from core.recovery.validator import RecoveryValidator
        from core.analysis.root_cause import RootCauseAnalyzer
        from core.repair.planner import RepairPlanner
        from core.repair.sandbox import SandboxExecutor
        from core.monitoring.monitor import PipelineMonitor
        from core.inference.engine import InferenceEngine

        self.characterizer = DatasetCharacterizer()
        self.task_detector = TaskDetector()
        self.feature_role_detector = FeatureRoleDetector()
        self.leakage_detector = LeakageDetector()
        self.preprocessing_recommender = PreprocessingRecommender()
        self.validation_selector = ValidationStrategySelector()
        self.candidate_generator = ModelCandidateGenerator()
        self.trainer = ModelTrainer()

        self.checkpoint_manager = CheckpointManager(root_dir=checkpoint_root)
        self.pipeline_executor = PipelineExecutor(
            checkpoint_manager=self.checkpoint_manager
        )

        self.fault_detector = FaultDetector()
        self.fault_localizer = FaultLocalizer()
        self.recovery_decision_engine = RecoveryDecisionEngine()
        self.recovery_executor = RecoveryExecutor(
            checkpoint_manager=self.checkpoint_manager
        )
        self.recovery_validator = RecoveryValidator()
        self.root_cause_analyzer = RootCauseAnalyzer()
        self.repair_planner = RepairPlanner()
        self.sandbox_executor = SandboxExecutor()

        self.monitor = PipelineMonitor()
        self.inference_engine = InferenceEngine()

        self._artifact_root = Path(artifact_root)
        self._artifact_root.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def run(
        self,
        df: pd.DataFrame,
        *,
        dataset_path: str = "unknown",
        target: str | None = None,
        task_type: str | None = None,
        max_candidates: int | None = None,
        save_artifact: bool = True,
    ) -> OrchestratorResult:
        """
        Execute the full AyaskX intelligent ML pipeline.

        Parameters
        ----------
        df             : input DataFrame
        dataset_path   : path or identifier of the dataset (for traceability)
        target         : target column name (auto-detected if None)
        task_type      : "classification"|"regression" (auto-detected if None)
        max_candidates : limit on number of model candidates to train
        save_artifact  : whether to persist the best model artifact to disk

        Returns
        -------
        OrchestratorResult — immutable, always returned (never raises).
        """

        execution_id = str(uuid.uuid4())
        started_at = _utc_now()
        warnings: list[str] = []

        try:
            fingerprint = _df_fingerprint(df)

            # ── Stage 1: Characterize ────────────────────────────────────────
            characterization = self.characterizer.characterize(
                df, dataset_path
            )

            ckpt_char = self.checkpoint_manager.create(
                execution_id=execution_id,
                node_id="characterization",
                artifact={"rows": characterization.rows,
                          "columns": characterization.columns,
                          "fingerprint": fingerprint},
                validation_status="passed",
            )

            # ── Stage 2: Task detection ──────────────────────────────────────
            task_result = self.task_detector.detect(df)
            resolved_target = target or task_result.target

            if not resolved_target:
                return self._fail(
                    execution_id=execution_id,
                    dataset_path=dataset_path,
                    fingerprint=fingerprint,
                    characterization=characterization,
                    task_detection=task_result,
                    message="Task detection could not identify a target column.",
                    warnings=warnings,
                    started_at=started_at,
                )

            resolved_task = task_type or task_result.task_type
            if resolved_task in ("spatial_classification", "spatial_regression"):
                resolved_task = resolved_task.split("_")[1]  # strip spatial prefix

            if task_result.warnings:
                warnings.extend(task_result.warnings)

            # ── Stage 3: Feature roles ───────────────────────────────────────
            role_report = self.feature_role_detector.detect(
                df, target=resolved_target
            )

            # ── Stage 4: Leakage detection ───────────────────────────────────
            leakage_report = self.leakage_detector.analyze(
                df, target=resolved_target
            )
            if leakage_report.risky_features:
                warnings.append(
                    f"Leakage risk detected in: {list(leakage_report.risky_features)}"
                )

            # ── Stage 5: Preprocessing plan ──────────────────────────────────
            prep_plan = self.preprocessing_recommender.recommend(
                df, target=resolved_target
            )

            # ── Stage 6: Validation strategy ─────────────────────────────────
            val_strategy = self.validation_selector.select(
                df,
                target=resolved_target,
            )

            # ── Stage 7: Model candidates ─────────────────────────────────────
            candidate_report = self.candidate_generator.generate(
                df=df,
                target=resolved_target,
                task_type=resolved_task,
            )

            candidates = tuple(
                c.name for c in candidate_report.candidates
            )
            if max_candidates:
                candidates = candidates[:max_candidates]

            if not candidates:
                return self._fail(
                    execution_id=execution_id,
                    dataset_path=dataset_path,
                    fingerprint=fingerprint,
                    characterization=characterization,
                    task_detection=task_result,
                    feature_roles=role_report,
                    leakage_report=leakage_report,
                    preprocessing_plan=prep_plan,
                    validation_strategy=val_strategy,
                    candidate_report=candidate_report,
                    message="No model candidates generated.",
                    warnings=warnings,
                    started_at=started_at,
                )

            # ── Stage 8: Training + evaluation ───────────────────────────────
            # Determine group/time/spatial columns from feature roles
            group_col = (
                role_report.identifier_columns[0]
                if role_report.identifier_columns else None
            )
            time_col = (
                role_report.temporal_columns[0]
                if role_report.temporal_columns else None
            )
            lat_col = (
                role_report.spatial_columns[0]
                if role_report.spatial_columns else None
            )
            lon_col = (
                role_report.spatial_columns[1]
                if len(role_report.spatial_columns) >= 2 else None
            )

            safe_df = self._apply_leakage_filter(df, leakage_report, resolved_target)

            try:
                training_result = self.trainer.train_and_evaluate(
                    df=safe_df,
                    target=resolved_target,
                    task_type=resolved_task,
                    candidates=candidates,
                    validation_strategy=val_strategy.strategy,
                    group_column=group_col,
                    time_column=time_col,
                    latitude_column=lat_col,
                    longitude_column=lon_col,
                )
            except ValueError:
                # Validation strategy incompatible with data (e.g. temporal
                # column parse failure, insufficient groups).
                # Fall back to random_holdout — adaptive, not hardcoded.
                warnings.append(
                    f"Validation strategy '{val_strategy.strategy}' failed "
                    f"for this data; falling back to random_holdout."
                )
                training_result = self.trainer.train_and_evaluate(
                    df=safe_df,
                    target=resolved_target,
                    task_type=resolved_task,
                    candidates=candidates,
                    validation_strategy="random_holdout",
                )


            ckpt_train = self.checkpoint_manager.create(
                execution_id=execution_id,
                node_id="training",
                artifact={
                    "best_model": training_result.best_model_name,
                    "best_score": training_result.best_score,
                    "fingerprint": fingerprint,
                },
                validation_status="passed",
            )

            # ── Stage 9: Monitoring ───────────────────────────────────────────
            if training_result.best_model_name and training_result.evaluations:
                best_eval = next(
                    (e for e in training_result.evaluations
                     if e.model_name == training_result.best_model_name),
                    training_result.evaluations[0],
                )
                self.monitor.check_model_metrics(
                    execution_id=execution_id,
                    model_name=best_eval.model_name,
                    task_type=resolved_task,
                    metrics=best_eval.metrics,
                )

            # ── Stage 10: Build ModelArtifact ─────────────────────────────────
            model_artifact = self._build_artifact(
                execution_id=execution_id,
                df=safe_df,
                target=resolved_target,
                task_type=resolved_task,
                training_result=training_result,
                feature_columns=[
                    c for c in safe_df.columns if c != resolved_target
                ],
                val_strategy=val_strategy,
                fingerprint=fingerprint,
                checkpoint_id=ckpt_train.checkpoint_id,
                group_col=group_col,
                time_col=time_col,
                lat_col=lat_col,
                lon_col=lon_col,
            )

            if save_artifact and model_artifact is not None:
                artifact_path = (
                    self._artifact_root
                    / f"{execution_id}_{model_artifact.model_name}.joblib"
                )
                try:
                    model_artifact.save(artifact_path)
                except Exception as exc:
                    warnings.append(f"Artifact save failed: {exc}")

            alerts = self.monitor.drain()

            return OrchestratorResult(
                execution_id=execution_id,
                dataset_path=dataset_path,
                dataset_fingerprint=fingerprint,
                characterization=characterization,
                task_detection=task_result,
                feature_roles=role_report,
                leakage_report=leakage_report,
                preprocessing_plan=prep_plan,
                validation_strategy=val_strategy,
                candidate_report=candidate_report,
                training_result=training_result,
                model_artifact=model_artifact,
                success=training_result.best_model_name is not None,
                message=(
                    f"Pipeline completed. Best model: "
                    f"{training_result.best_model_name} "
                    f"(score={training_result.best_score:.4f})"
                    if training_result.best_score is not None
                    else "Pipeline completed."
                ),
                warnings=tuple(warnings),
                alerts=alerts,
                started_at=started_at,
                completed_at=_utc_now(),
            )

        except Exception as exc:
            return OrchestratorResult(
                execution_id=execution_id,
                dataset_path=dataset_path,
                dataset_fingerprint=_df_fingerprint(df) if df is not None else "",
                success=False,
                message=f"Pipeline error: {type(exc).__name__}: {exc}",
                warnings=tuple(warnings),
                started_at=started_at,
                completed_at=_utc_now(),
            )

    def predict(
        self,
        artifact: Any,
        data: pd.DataFrame,
        *,
        request_id: str | None = None,
    ) -> Any:
        """
        Run inference using a stored ModelArtifact.

        Parameters
        ----------
        artifact   : ModelArtifact from a previous run()
        data       : input DataFrame
        request_id : optional request identifier

        Returns
        -------
        InferenceResult
        """
        from core.inference.engine import InferenceRequest

        req = InferenceRequest(
            request_id=request_id or str(uuid.uuid4()),
            execution_id=artifact.execution_id,
            data=data,
        )
        return self.inference_engine.predict(artifact, req)

    def analyze_and_heal(
        self,
        pipeline_execution: Any,
        events: tuple = (),
    ) -> dict[str, Any]:
        """
        Run the full self-healing analysis pipeline on a failed execution.

        Returns a dict with:
            fault, localization, root_cause, decision, recovery_result, repair_plan
        """
        lkg = self.pipeline_executor.last_known_good_checkpoint(
            pipeline_execution.execution_id
        )

        fault = self.fault_detector.detect(pipeline_execution)
        localization = self.fault_localizer.localize(
            pipeline_execution, fault, events=events
        )
        root_cause = self.root_cause_analyzer.analyze(
            pipeline_execution, fault, localization, events=events
        )
        decision = self.recovery_decision_engine.decide(
            pipeline_execution, fault, localization,
            last_known_good_checkpoint=lkg,
        )
        recovery_result = self.recovery_executor.execute(decision)

        lkg_id = getattr(lkg, "checkpoint_id", None) if lkg else None
        repair_plan = self.repair_planner.plan(
            root_cause,
            last_known_good_checkpoint=lkg_id,
        )

        return {
            "fault": fault,
            "localization": localization,
            "root_cause": root_cause,
            "decision": decision,
            "recovery_result": recovery_result,
            "repair_plan": repair_plan,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _apply_leakage_filter(
        self,
        df: pd.DataFrame,
        leakage_report: Any,
        target: str,
    ) -> pd.DataFrame:
        """Drop risky features before training."""
        risky = set(leakage_report.risky_features)
        cols_to_drop = [
            c for c in risky
            if c in df.columns and c != target
        ]
        if cols_to_drop:
            return df.drop(columns=cols_to_drop)
        return df

    def _build_artifact(
        self,
        *,
        execution_id: str,
        df: pd.DataFrame,
        target: str,
        task_type: str,
        training_result: Any,
        feature_columns: list[str],
        val_strategy: Any,
        fingerprint: str,
        checkpoint_id: str | None,
        group_col: str | None,
        time_col: str | None,
        lat_col: str | None,
        lon_col: str | None,
    ) -> Any:
        """Build a ModelArtifact for the best-performing model.

        Reuses the fitted sklearn Pipeline already stored by self.trainer
        during the training stage — no second training pass required.
        """
        from core.inference.engine import ModelArtifact

        if not training_result.best_model_name:
            return None

        best_eval = next(
            (e for e in training_result.evaluations
             if e.model_name == training_result.best_model_name),
            None,
        )
        if not best_eval:
            return None

        # Retrieve the already-fitted pipeline (stored during train_on_split)
        fitted_pipeline = self.trainer.get_fitted_pipeline(
            training_result.best_model_name
        )

        return ModelArtifact(
            model_name=training_result.best_model_name,
            task_type=task_type,
            execution_id=execution_id,
            pipeline=fitted_pipeline,
            feature_columns=feature_columns,
            target_column=target,
            metrics=best_eval.metrics,
            validation_strategy=val_strategy.strategy,
            dataset_fingerprint=fingerprint,
            checkpoint_id=checkpoint_id,
        )


    def _fail(self, **kwargs) -> OrchestratorResult:
        started_at = kwargs.pop("started_at", _utc_now())
        warnings = kwargs.pop("warnings", [])
        return OrchestratorResult(
            **{k: v for k, v in kwargs.items()
               if k in OrchestratorResult.__dataclass_fields__},
            success=False,
            warnings=tuple(warnings),
            started_at=started_at,
            completed_at=_utc_now(),
        )
