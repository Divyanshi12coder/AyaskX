"""
core/platform/orchestrator.py
------------------------------
AyaskX Core Platform Orchestrator.

Phases B + C: PIPELINE UNIFICATION + EXECUTION ENGINE

This module provides the single coherent entry point for the AyaskX
intelligent ML pipeline.

Pipeline:

    Dataset
        |
        v
    Characterization
        |
        v
    Task Detection
        |
        v
    Feature Role Detection
        |
        v
    Leakage Detection
        |
        v
    Preprocessing Recommendation
        |
        v
    Validation Strategy
        |
        v
    Model Candidate Generation
        |
        v
    Model Training + Evaluation
        |
        v
    Best Model Artifact
        |
        v
    Inference

Self-healing:

    Failed Execution
        |
        v
    Persistence -> Domain Adapter
        |
        v
    Fault Detection
        |
        v
    Fault Localization
        |
        v
    Root Cause Analysis
        |
        v
    Recovery Decision
        |
        v
    Recovery Execution
        |
        v
    Recovery Validation
        |
        v
    Repair Planning

Important:
- Persistence-layer PipelineExecution and domain PipelineExecution are
  different models.
- SQLAlchemy persistence stores status as a string.
- Self-healing modules expect PipelineStatus enum and NodeExecution data.
- analyze_and_heal() therefore normalizes persistence records into the
  domain execution contract before invoking self-healing modules.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from core.pipeline.checkpoints.manager import CheckpointManager

import pandas as pd

from core.storage import ExecutionRepository


from core.pipeline.executor import (
    PipelineExecution as DomainPipelineExecution,
    NodeExecution,
)

from core.pipeline.status import (
    NodeStatus,
    PipelineStatus,
)


# ============================================================================
# Utility helpers
# ============================================================================


def _utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _df_fingerprint(df: pd.DataFrame) -> str:
    """
    Produce a deterministic lightweight fingerprint for a DataFrame.

    The fingerprint contains:
    - dataframe dimensions
    - sorted column names
    - sampled content hash
    """

    shape_part = f"{df.shape[0]}x{df.shape[1]}"

    cols_part = ",".join(
        sorted(
            str(column)
            for column in df.columns.tolist()
        )
    )

    try:
        if len(df) >= 2:
            sample = df.sample(
                min(100, len(df)),
                random_state=42,
            )
        else:
            sample = df

        content_part = hashlib.md5(
            pd.util.hash_pandas_object(
                sample,
                index=True,
            ).values.tobytes()
        ).hexdigest()[:16]

    except Exception:
        content_part = "nohash"

    return (
        f"sha:{shape_part}:"
        f"{content_part}:"
        f"{hashlib.md5(cols_part.encode('utf-8')).hexdigest()[:8]}"
    )


# ============================================================================
# OrchestratorResult
# ============================================================================


@dataclass(frozen=True)
class OrchestratorResult:
    """
    Immutable top-level result returned by AyaskXOrchestrator.run().
    """

    execution_id: str

    dataset_path: str

    dataset_fingerprint: str

    # ------------------------------------------------------------------
    # Pipeline stage outputs
    # ------------------------------------------------------------------

    characterization: Any = None

    task_detection: Any = None

    feature_roles: Any = None

    leakage_report: Any = None

    preprocessing_plan: Any = None

    validation_strategy: Any = None

    candidate_report: Any = None

    training_result: Any = None

    model_artifact: Any = None

    # ------------------------------------------------------------------
    # Self-healing outputs
    # ------------------------------------------------------------------

    fault_report: Any = None

    fault_localization: Any = None

    root_cause_report: Any = None

    recovery_decision: Any = None

    recovery_result: Any = None

    repair_plan: Any = None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    pipeline_execution: Any = None

    success: bool = False

    message: str = ""

    warnings: tuple[str, ...] = ()

    alerts: tuple[Any, ...] = ()

    started_at: datetime = field(
        default_factory=_utc_now
    )

    completed_at: datetime | None = None

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def to_summary(self) -> dict[str, Any]:
        """
        Return a JSON-serializable summary.

        This method intentionally avoids serializing large model objects.
        """

        td = self.task_detection

        vs = self.validation_strategy

        tr = self.training_result

        cr = self.candidate_report

        candidates = []

        for candidate in getattr(
            cr,
            "candidates",
            [],
        ):
            candidates.append(
                getattr(
                    candidate,
                    "name",
                    str(candidate),
                )
            )

        return {
            "execution_id": self.execution_id,
            "dataset_path": self.dataset_path,
            "dataset_fingerprint": self.dataset_fingerprint,
            "success": self.success,
            "message": self.message,
            "task_type": getattr(
                td,
                "task_type",
                None,
            ),
            "target": getattr(
                td,
                "target",
                None,
            ),
            "validation_strategy": getattr(
                vs,
                "strategy",
                None,
            ),
            "candidates": candidates,
            "best_model": getattr(
                tr,
                "best_model_name",
                None,
            ),
            "best_score": getattr(
                tr,
                "best_score",
                None,
            ),
            "warnings": list(
                self.warnings
            ),
            "alerts": len(
                self.alerts
            ),
            "started_at": (
                self.started_at.isoformat()
                if self.started_at
                else None
            ),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at
                else None
            ),
        }


# ============================================================================
# AyaskXOrchestrator
# ============================================================================


class AyaskXOrchestrator:
    """
    AyaskX Core Platform Orchestrator.

    Connects the existing AyaskX modules into one coherent pipeline.

    The orchestrator does not duplicate model-training, preprocessing,
    validation, fault-detection, or recovery logic. It coordinates the
    existing modules.

    Example
    -------

    orchestrator = AyaskXOrchestrator()

    result = orchestrator.run(
        df,
        dataset_path="train.csv",
        target="target",
    )

    inference = orchestrator.predict(
        result.model_artifact,
        new_dataframe,
    )
    """

    # ========================================================================
    # Initialization
    # ========================================================================

    def __init__(
        self,
        checkpoint_root: str | Path = ".ayask_checkpoints",
        artifact_root: str | Path = ".ayask_artifacts",
        checkpoint_manager: "CheckpointManager | None" = None,
    ) -> None:

        # ------------------------------------------------------------------
        # Existing ML modules
        # ------------------------------------------------------------------

        from core.datasets.characterization.characterizer import (
            DatasetCharacterizer,
        )

        from core.task_detection.detector import (
            TaskDetector,
        )

        from core.feature_roles.detector import (
            FeatureRoleDetector,
        )

        from core.leakage.detector import (
            LeakageDetector,
        )

        from core.preprocessing.recommender import (
            PreprocessingRecommender,
        )

        from core.validation.strategy import (
            ValidationStrategySelector,
        )

        from core.models.candidates import (
            ModelCandidateGenerator,
        )

        from core.models.trainer import (
            ModelTrainer,
        )

        # ------------------------------------------------------------------
        # Pipeline infrastructure
        # ------------------------------------------------------------------

        from core.pipeline.executor import (
            PipelineExecutor,
        )

        from core.pipeline.checkpoints.manager import (
            CheckpointManager,
        )

        # ------------------------------------------------------------------
        # Self-healing modules
        # ------------------------------------------------------------------

        from core.fault.detector import (
            FaultDetector,
        )

        from core.fault.localizer import (
            FaultLocalizer,
        )

        from core.recovery.decision import (
            RecoveryDecisionEngine,
        )

        from core.recovery.executor import (
            RecoveryExecutor,
        )

        from core.recovery.validator import (
            RecoveryValidator,
        )

        from core.analysis.root_cause import (
            RootCauseAnalyzer,
        )

        from core.repair.planner import (
            RepairPlanner,
        )

        from core.repair.sandbox import (
            SandboxExecutor,
        )

        # ------------------------------------------------------------------
        # Monitoring / inference
        # ------------------------------------------------------------------

        from core.monitoring.monitor import (
            PipelineMonitor,
        )

        from core.inference.engine import (
            InferenceEngine,
        )

        # ------------------------------------------------------------------
        # Instantiate ML modules
        # ------------------------------------------------------------------

        self.characterizer = DatasetCharacterizer()

        self.task_detector = TaskDetector()

        self.feature_role_detector = FeatureRoleDetector()

        self.leakage_detector = LeakageDetector()

        self.preprocessing_recommender = (
            PreprocessingRecommender()
        )

        self.validation_selector = (
            ValidationStrategySelector()
        )

        self.candidate_generator = (
            ModelCandidateGenerator()
        )

        self.trainer = ModelTrainer()

        # ------------------------------------------------------------------
        # Checkpoint / execution engine
        # ------------------------------------------------------------------

        self.checkpoint_manager = (
             checkpoint_manager
             if checkpoint_manager is not None
             else CheckpointManager(
                root_dir=checkpoint_root
            )
        )

        self.pipeline_executor = PipelineExecutor(
            checkpoint_manager=self.checkpoint_manager
        )

        # ------------------------------------------------------------------
        # Self-healing
        # ------------------------------------------------------------------

        self.fault_detector = FaultDetector()

        self.fault_localizer = FaultLocalizer()

        self.recovery_decision_engine = (
            RecoveryDecisionEngine()
        )

        self.recovery_executor = RecoveryExecutor(
            checkpoint_manager=self.checkpoint_manager
        )

        self.recovery_validator = RecoveryValidator()

        self.root_cause_analyzer = RootCauseAnalyzer()

        self.repair_planner = RepairPlanner()

        self.sandbox_executor = SandboxExecutor()

        # ------------------------------------------------------------------
        # Monitoring / inference
        # ------------------------------------------------------------------

        self.monitor = PipelineMonitor()

        self.inference_engine = InferenceEngine()

        # ------------------------------------------------------------------
        # Persistence
        # ------------------------------------------------------------------

        self.execution_repository = (
            ExecutionRepository()
        )

        # ------------------------------------------------------------------
        # Artifact directory
        # ------------------------------------------------------------------

        self._artifact_root = Path(
            artifact_root
        )

        self._artifact_root.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ========================================================================
    # RUN
    # ========================================================================

    def run(
        self,
        df: pd.DataFrame,
        *,
        execution_id: str | None = None,
        dataset_path: str = "unknown",
        target: str | None = None,
        task_type: str | None = None,
        max_candidates: int | None = None,
        save_artifact: bool = True,
    ) -> OrchestratorResult:
        """
        Execute the full AyaskX intelligent ML pipeline.

        The method always returns an OrchestratorResult rather than exposing
        an unhandled pipeline exception to the caller.
        """

        # API callers may allocate an execution ID before dispatching work so
        # that HTTP status, checkpoints, artifacts, and core persistence all
        # share one traceable identifier. Direct core callers keep the prior
        # behaviour of receiving a new UUID for every run.
        execution_id = execution_id or str(uuid.uuid4())

        started_at = _utc_now()

        warnings: list[str] = []

        fingerprint = ""

        # ------------------------------------------------------------------
        # Input validation
        # ------------------------------------------------------------------

        if not isinstance(
            df,
            pd.DataFrame,
        ):
            return self._fail(
                execution_id=execution_id,
                dataset_path=dataset_path,
                fingerprint="",
                message=(
                    "Input must be a pandas DataFrame."
                ),
                warnings=warnings,
                started_at=started_at,
            )

        fingerprint = _df_fingerprint(df)

        # ------------------------------------------------------------------
        # Persist execution start
        # ------------------------------------------------------------------

        try:

            self.execution_repository.create_execution(
                execution_id=execution_id,
                dataset_path=dataset_path,
                dataset_fingerprint=fingerprint,
                status="started",
            )

        except Exception as exc:

            warnings.append(
                "Execution persistence initialization failed: "
                f"{type(exc).__name__}: {exc}"
            )

        # ==================================================================
        # Main pipeline
        # ==================================================================

        try:

            # ==============================================================
            # Stage 1: Dataset characterization
            # ==============================================================

            characterization = (
                self.characterizer.characterize(
                    df,
                    dataset_path,
                )
            )

            ckpt_char = (
                self.checkpoint_manager.create(
                    execution_id=execution_id,
                    node_id="characterization",
                    artifact={
                        "rows": characterization.rows,
                        "columns": characterization.columns,
                        "fingerprint": fingerprint,
                    },
                    validation_status="passed",
                )
            )

            # ==============================================================
            # Stage 2: Task detection
            # ==============================================================

            task_result = (
                self.task_detector.detect(
                    df
                )
            )

            resolved_target = (
                target
                or getattr(
                    task_result,
                    "target",
                    None,
                )
            )

            if not resolved_target:

                return self._fail(
                    execution_id=execution_id,
                    dataset_path=dataset_path,
                    fingerprint=fingerprint,
                    characterization=characterization,
                    task_detection=task_result,
                    message=(
                        "Task detection could not identify "
                        "a target column."
                    ),
                    warnings=warnings,
                    started_at=started_at,
                )

            resolved_task = (
                task_type
                or getattr(
                    task_result,
                    "task_type",
                    None,
                )
            )

            if resolved_task in (
                "spatial_classification",
                "spatial_regression",
            ):
                resolved_task = (
                    resolved_task.split("_")[1]
                )

            task_warnings = getattr(
                task_result,
                "warnings",
                None,
            )

            if task_warnings:
                warnings.extend(
                    task_warnings
                )

            # ==============================================================
            # Stage 3: Feature roles
            # ==============================================================

            role_report = (
                self.feature_role_detector.detect(
                    df,
                    target=resolved_target,
                )
            )

            # ==============================================================
            # Stage 4: Leakage detection
            # ==============================================================

            leakage_report = (
                self.leakage_detector.analyze(
                    df,
                    target=resolved_target,
                )
            )

            risky_features = getattr(
                leakage_report,
                "risky_features",
                (),
            )

            if risky_features:

                warnings.append(
                    "Leakage risk detected in: "
                    f"{list(risky_features)}"
                )

            # ==============================================================
            # Stage 5: Preprocessing recommendation
            # ==============================================================

            prep_plan = (
                self.preprocessing_recommender.recommend(
                    df,
                    target=resolved_target,
                )
            )

            # ==============================================================
            # Stage 6: Validation strategy
            # ==============================================================

            val_strategy = (
                self.validation_selector.select(
                    df,
                    target=resolved_target,
                )
            )

            # ==============================================================
            # Stage 7: Candidate generation
            # ==============================================================

            candidate_report = (
                self.candidate_generator.generate(
                    df=df,
                    target=resolved_target,
                    task_type=resolved_task,
                )
            )

            candidates = tuple(
                getattr(
                    candidate,
                    "name",
                    str(candidate),
                )
                for candidate
                in getattr(
                    candidate_report,
                    "candidates",
                    (),
                )
            )

            # --------------------------------------------------------------
            # Candidate limit
            # --------------------------------------------------------------

            if max_candidates is not None:

                if max_candidates <= 0:

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
                        message=(
                            "max_candidates must be "
                            "greater than zero."
                        ),
                        warnings=warnings,
                        started_at=started_at,
                    )

                candidates = candidates[
                    :max_candidates
                ]

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
                    message=(
                        "No model candidates generated."
                    ),
                    warnings=warnings,
                    started_at=started_at,
                )

            # ==============================================================
            # Stage 8: Determine structural columns
            # ==============================================================

            identifier_columns = getattr(
                role_report,
                "identifier_columns",
                (),
            )

            temporal_columns = getattr(
                role_report,
                "temporal_columns",
                (),
            )

            spatial_columns = getattr(
                role_report,
                "spatial_columns",
                (),
            )

            group_col = (
                identifier_columns[0]
                if identifier_columns
                else None
            )

            time_col = (
                temporal_columns[0]
                if temporal_columns
                else None
            )

            lat_col = (
                spatial_columns[0]
                if spatial_columns
                else None
            )

            lon_col = (
                spatial_columns[1]
                if len(spatial_columns) >= 2
                else None
            )

            # ==============================================================
            # Leakage-safe training dataframe
            # ==============================================================

            safe_df = self._apply_leakage_filter(
                df,
                leakage_report,
                resolved_target,
            )

            # ==============================================================
            # Stage 9: Model training + evaluation
            # ==============================================================

            try:

                training_result = (
                    self.trainer.train_and_evaluate(
                        df=safe_df,
                        target=resolved_target,
                        task_type=resolved_task,
                        candidates=candidates,
                        validation_strategy=(
                            val_strategy.strategy
                        ),
                        group_column=group_col,
                        time_column=time_col,
                        latitude_column=lat_col,
                        longitude_column=lon_col,
                    )
                )

            except ValueError:

                warnings.append(
                    f"Validation strategy "
                    f"'{val_strategy.strategy}' "
                    "was incompatible with the dataset; "
                    "falling back to random_holdout."
                )

                training_result = (
                    self.trainer.train_and_evaluate(
                        df=safe_df,
                        target=resolved_target,
                        task_type=resolved_task,
                        candidates=candidates,
                        validation_strategy="random_holdout",
                    )
                )

            # ==============================================================
            # Training checkpoint
            # ==============================================================

            ckpt_train = (
                self.checkpoint_manager.create(
                    execution_id=execution_id,
                    node_id="training",
                    artifact={
                        "best_model": (
                            training_result.best_model_name
                        ),
                        "best_score": (
                            training_result.best_score
                        ),
                        "fingerprint": fingerprint,
                    },
                    validation_status="passed",
                )
            )

            # ==============================================================
            # Stage 10: Monitoring
            # ==============================================================

            if (
                training_result.best_model_name
                and training_result.evaluations
            ):

                best_eval = next(
                    (
                        evaluation
                        for evaluation
                        in training_result.evaluations
                        if (
                            evaluation.model_name
                            == training_result.best_model_name
                        )
                    ),
                    training_result.evaluations[0],
                )

                self.monitor.check_model_metrics(
                    execution_id=execution_id,
                    model_name=best_eval.model_name,
                    task_type=resolved_task,
                    metrics=best_eval.metrics,
                )

            # ==============================================================
            # Stage 11: Model artifact
            # ==============================================================

            model_artifact = (
                self._build_artifact(
                    execution_id=execution_id,
                    df=safe_df,
                    target=resolved_target,
                    task_type=resolved_task,
                    training_result=training_result,
                    feature_columns=[
                        column
                        for column in safe_df.columns
                        if column != resolved_target
                    ],
                    val_strategy=val_strategy,
                    fingerprint=fingerprint,
                    checkpoint_id=(
                        ckpt_train.checkpoint_id
                    ),
                    group_col=group_col,
                    time_col=time_col,
                    lat_col=lat_col,
                    lon_col=lon_col,
                )
            )

            # ==============================================================
            # Persist artifact
            # ==============================================================

            artifact_path = None

            if (
                save_artifact
                and model_artifact is not None
            ):

                artifact_path = (
                    self._artifact_root
                    / (
                        f"{execution_id}_"
                        f"{model_artifact.model_name}.joblib"
                    )
                )

                try:

                    model_artifact.save(
                        artifact_path
                    )

                except Exception as exc:

                    warnings.append(
                        "Artifact save failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

            # ==============================================================
            # Monitoring alerts
            # ==============================================================

            alerts = self.monitor.drain()

            final_success = (
                training_result.best_model_name
                is not None
            )

            final_message = (
                (
                    "Pipeline completed. Best model: "
                    f"{training_result.best_model_name} "
                    f"(score="
                    f"{training_result.best_score:.4f})"
                )
                if training_result.best_score is not None
                else "Pipeline completed."
            )

            # ==============================================================
            # Persist successful execution
            # ==============================================================

            self._persist_execution_completion(
                execution_id=execution_id,
                success=final_success,
                message=final_message,
                result={
                    "dataset_path": dataset_path,
                    "dataset_fingerprint": fingerprint,
                    "target": resolved_target,
                    "task_type": resolved_task,
                    "best_model": (
                        training_result.best_model_name
                    ),
                    "best_score": (
                        training_result.best_score
                    ),
                    "artifact_path": (
                        str(artifact_path)
                        if artifact_path
                        else None
                    ),
                    "warnings": list(warnings),
                },
            )

            # ==============================================================
            # Return result
            # ==============================================================

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
                success=final_success,
                message=final_message,
                warnings=tuple(warnings),
                alerts=alerts,
                started_at=started_at,
                completed_at=_utc_now(),
            )

        # ==================================================================
        # Global pipeline failure
        # ==================================================================

        except Exception as exc:

            error_message = (
                "Pipeline error: "
                f"{type(exc).__name__}: {exc}"
            )

            # --------------------------------------------------------------
            # Persist failure
            # --------------------------------------------------------------

            self._persist_execution_completion(
                execution_id=execution_id,
                success=False,
                message=error_message,
                result={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "dataset_path": dataset_path,
                    "dataset_fingerprint": fingerprint,
                },
            )

            # --------------------------------------------------------------
            # Persist fault event
            # --------------------------------------------------------------

            self._persist_fault(
                execution_id=execution_id,
                fault_type=type(exc).__name__,
                severity="high",
                component="orchestrator",
                message=str(exc),
                evidence={
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "node_id": "orchestrator",
                },
            )

            return OrchestratorResult(
                execution_id=execution_id,
                dataset_path=dataset_path,
                dataset_fingerprint=fingerprint,
                success=False,
                message=error_message,
                warnings=tuple(warnings),
                started_at=started_at,
                completed_at=_utc_now(),
            )

    # ========================================================================
    # INFERENCE
    # ========================================================================

    def predict(
        self,
        artifact: Any,
        data: pd.DataFrame,
        *,
        request_id: str | None = None,
    ) -> Any:
        """
        Run inference using a ModelArtifact.
        """

        from core.inference.engine import (
            InferenceRequest,
        )

        req = InferenceRequest(
            request_id=(
                request_id
                or str(uuid.uuid4())
            ),
            execution_id=artifact.execution_id,
            data=data,
        )

        return self.inference_engine.predict(
            artifact,
            req,
        )

    # ========================================================================
    # SELF-HEALING
    # ========================================================================

    def analyze_and_heal(
        self,
        pipeline_execution: Any,
        events: tuple = (),
    ) -> dict[str, Any]:
        """
        Run the complete deterministic self-healing chain.

        Accepts BOTH:

        1. Domain PipelineExecution
        2. SQLAlchemy persistence PipelineExecution

        Persistence execution is automatically adapted into the domain
        execution expected by FaultDetector, FaultLocalizer, RootCauseAnalyzer
        and RecoveryDecisionEngine.

        Chain:

            Persistence Execution
                    |
                    v
            Domain Execution Adapter
                    |
                    v
            FaultDetector
                    |
                    v
            FaultLocalizer
                    |
                    v
            RootCauseAnalyzer
                    |
                    v
            RecoveryDecisionEngine
                    |
                    v
            RecoveryExecutor
                    |
                    v
            RecoveryValidator
                    |
                    v
            RepairPlanner

        No production code is generated.
        No arbitrary production file mutation is performed here.
        """

        # ------------------------------------------------------------------
        # 1. Normalize execution
        # ------------------------------------------------------------------

        domain_execution = (
            self._to_domain_execution(
                pipeline_execution
            )
        )

        execution_id = (
            domain_execution.execution_id
        )

        # ------------------------------------------------------------------
        # 2. Last known good checkpoint
        # ------------------------------------------------------------------

        lkg = (
            self.pipeline_executor
            .last_known_good_checkpoint(
                execution_id
            )
        )

        # ------------------------------------------------------------------
        # 3. Fault detection
        # ------------------------------------------------------------------

        fault = (
            self.fault_detector.detect(
                domain_execution
            )
        )

        # ------------------------------------------------------------------
        # 4. Persist detected fault
        # ------------------------------------------------------------------

        if fault.detected:

            self._persist_fault(
                execution_id=execution_id,
                fault_type=(
                    fault.fault_type.value
                ),
                severity=(
                    fault.severity.value
                ),
                component=fault.observed_node,
                message=fault.message,
                evidence=fault.evidence,
            )

        # ------------------------------------------------------------------
        # 5. Localization
        # ------------------------------------------------------------------

        localization = (
            self.fault_localizer.localize(
                domain_execution,
                fault,
                events=events,
            )
        )

        # ------------------------------------------------------------------
        # 6. Root cause
        # ------------------------------------------------------------------

        root_cause = (
            self.root_cause_analyzer.analyze(
                domain_execution,
                fault,
                localization,
                events=events,
            )
        )

        # ------------------------------------------------------------------
        # 7. Recovery decision
        # ------------------------------------------------------------------

        decision = (
            self.recovery_decision_engine.decide(
                domain_execution,
                fault,
                localization,
                last_known_good_checkpoint=lkg,
            )
        )

        # ------------------------------------------------------------------
        # 8. Recovery execution
        # ------------------------------------------------------------------

        recovery_result = (
            self.recovery_executor.execute(
                decision
            )
        )

        # ------------------------------------------------------------------
        # 9. Recovery persistence
        # ------------------------------------------------------------------

        self._persist_recovery_result(
            execution_id=execution_id,
            decision=decision,
            recovery_result=recovery_result,
        )

        # ------------------------------------------------------------------
        # 10. Recovery validation
        # ------------------------------------------------------------------

        validation_result = None

        recovered_node = getattr(
            recovery_result,
            "node_execution",
            None,
        )

        if recovered_node is not None:

            try:

                validation_result = (
                    self.recovery_validator
                    .validate_node_execution(
                        recovered_node
                    )
                )

            except Exception:
                validation_result = None

        # ------------------------------------------------------------------
        # 11. Repair planning
        # ------------------------------------------------------------------

        lkg_id = (
            getattr(
                lkg,
                "checkpoint_id",
                None,
            )
            if lkg
            else None
        )

        repair_plan = (
            self.repair_planner.plan(
                root_cause,
                last_known_good_checkpoint=lkg_id,
            )
        )

        # ------------------------------------------------------------------
        # 12. Return complete result
        # ------------------------------------------------------------------

        return {
            "fault": fault,
            "localization": localization,
            "root_cause": root_cause,
            "decision": decision,
            "recovery_result": recovery_result,
            "recovery_validation": validation_result,
            "repair_plan": repair_plan,
            "domain_execution": domain_execution,
        }

    # ========================================================================
    # DOMAIN EXECUTION ADAPTER
    # ========================================================================

    def _to_domain_execution(
        self,
        pipeline_execution: Any,
    ) -> DomainPipelineExecution:
        """
        Convert a persistence-layer execution into the domain execution
        contract expected by the self-healing subsystem.

        This is the critical compatibility boundary.

        SQLAlchemy model:

            status -> "failed"
            created_at
            completed_at

        Domain model:

            status -> PipelineStatus.FAILED
            nodes -> tuple[NodeExecution, ...]
            started_at
            finished_at

        Persisted FaultEvent records are converted into conservative
        synthetic failed NodeExecution objects.

        If no FaultEvent exists but the execution itself is marked failed,
        a synthetic orchestrator-level failed node is created so the
        self-healing chain can still reason about the failure instead of
        crashing with:

            AttributeError: 'PipelineExecution' object has no attribute
            'failed_node'
        """

        # ------------------------------------------------------------------
        # Already domain execution
        # ------------------------------------------------------------------

        if isinstance(
            pipeline_execution,
            DomainPipelineExecution,
        ):

            return pipeline_execution

        # ------------------------------------------------------------------
        # Basic execution identity
        # ------------------------------------------------------------------

        execution_id = str(
            getattr(
                pipeline_execution,
                "execution_id",
                "",
            )
        )

        if not execution_id:

            raise ValueError(
                "Pipeline execution does not contain "
                "a valid execution_id."
            )

        # ------------------------------------------------------------------
        # Normalize status
        # ------------------------------------------------------------------

        raw_status = getattr(
            pipeline_execution,
            "status",
            PipelineStatus.FAILED,
        )

        domain_status = (
            self._normalize_pipeline_status(
                raw_status
            )
        )

        # ------------------------------------------------------------------
        # Timestamps
        # ------------------------------------------------------------------

        created_at = getattr(
            pipeline_execution,
            "created_at",
            None,
        )

        completed_at = getattr(
            pipeline_execution,
            "completed_at",
            None,
        )

        started_at = (
            created_at
            or getattr(
                pipeline_execution,
                "started_at",
                None,
            )
            or _utc_now()
        )

        finished_at = (
            completed_at
            or getattr(
                pipeline_execution,
                "finished_at",
                None,
            )
        )

        # ------------------------------------------------------------------
        # Retrieve persisted faults
        # ------------------------------------------------------------------

        persisted_faults = []

        try:

            persisted_faults = (
                self.execution_repository
                .get_faults(
                    execution_id
                )
            )

        except Exception:

            persisted_faults = []

        # ------------------------------------------------------------------
        # Convert persisted faults to NodeExecution
        # ------------------------------------------------------------------

        nodes: list[NodeExecution] = []

        for index, fault_event in enumerate(
            persisted_faults
        ):

            evidence = getattr(
                fault_event,
                "evidence",
                None,
            )

            if not isinstance(
                evidence,
                dict,
            ):
                evidence = {}

            node_id = (
                getattr(
                    fault_event,
                    "component",
                    None,
                )
                or evidence.get(
                    "node_id"
                )
                or f"persisted_fault_{index}"
            )

            error_type = (
                evidence.get(
                    "error_type"
                )
                or getattr(
                    fault_event,
                    "fault_type",
                    None,
                )
                or "UnknownFault"
            )

            error_message = (
                getattr(
                    fault_event,
                    "message",
                    None,
                )
                or evidence.get(
                    "error_message"
                )
                or "Persisted fault event."
            )

            output_metadata = {
                "persistence_source": (
                    "fault_events"
                ),
                "fault_event_id": getattr(
                    fault_event,
                    "id",
                    None,
                ),
                "fault_type": str(
                    getattr(
                        fault_event,
                        "fault_type",
                        "unknown",
                    )
                ),
                "severity": str(
                    getattr(
                        fault_event,
                        "severity",
                        "unknown",
                    )
                ),
            }

            if evidence:
                output_metadata[
                    "evidence"
                ] = dict(evidence)

            nodes.append(
                NodeExecution(
                    execution_id=execution_id,
                    node_id=str(node_id),
                    status=NodeStatus.FAILED,
                    started_at=started_at,
                    finished_at=(
                        finished_at
                        or _utc_now()
                    ),
                    input_metadata={},
                    output_metadata=(
                        output_metadata
                    ),
                    error_type=str(
                        error_type
                    ),
                    error_message=str(
                        error_message
                    ),
                    checkpoint_id=None,
                )
            )

        # ------------------------------------------------------------------
        # If failed execution has no persisted fault event
        # ------------------------------------------------------------------

        if (
            domain_status
            in (
                PipelineStatus.FAILED,
                PipelineStatus.ROLLED_BACK,
            )
            and not nodes
        ):

            persisted_message = getattr(
                pipeline_execution,
                "message",
                None,
            )

            persisted_result = getattr(
                pipeline_execution,
                "result",
                None,
            )

            error_type = "PersistedExecutionFailure"

            error_message = (
                persisted_message
                or "Execution was marked failed in persistence."
            )

            evidence: dict[str, Any] = {
                "persistence_source": (
                    "pipeline_executions"
                ),
                "execution_status": str(
                    raw_status
                ),
            }

            if isinstance(
                persisted_result,
                dict,
            ):

                evidence[
                    "result"
                ] = dict(
                    persisted_result
                )

                if persisted_result.get(
                    "error_type"
                ):
                    error_type = str(
                        persisted_result[
                            "error_type"
                        ]
                    )

                if persisted_result.get(
                    "error"
                ):
                    error_message = str(
                        persisted_result[
                            "error"
                        ]
                    )

            nodes.append(
                NodeExecution(
                    execution_id=execution_id,
                    node_id="persisted_execution",
                    status=NodeStatus.FAILED,
                    started_at=started_at,
                    finished_at=(
                        finished_at
                        or _utc_now()
                    ),
                    input_metadata={},
                    output_metadata=evidence,
                    error_type=error_type,
                    error_message=error_message,
                    checkpoint_id=None,
                )
            )

        # ------------------------------------------------------------------
        # For non-failed execution with no nodes
        # ------------------------------------------------------------------

        if (
            domain_status
            == PipelineStatus.SUCCESS
            and not nodes
        ):

            nodes.append(
                NodeExecution(
                    execution_id=execution_id,
                    node_id="persisted_execution",
                    status=NodeStatus.SUCCESS,
                    started_at=started_at,
                    finished_at=(
                        finished_at
                        or _utc_now()
                    ),
                    input_metadata={},
                    output_metadata={
                        "persistence_source": (
                            "pipeline_executions"
                        ),
                        "status": "success",
                    },
                    error_type=None,
                    error_message=None,
                    checkpoint_id=None,
                )
            )

        # ------------------------------------------------------------------
        # Build domain execution
        # ------------------------------------------------------------------

        return DomainPipelineExecution(
            execution_id=execution_id,
            status=domain_status,
            nodes=tuple(nodes),
            started_at=started_at,
            finished_at=finished_at,
        )

    # ========================================================================
    # STATUS NORMALIZATION
    # ========================================================================

    @staticmethod
    def _normalize_pipeline_status(
        raw_status: Any,
    ) -> PipelineStatus:
        """
        Normalize enum/string persistence status into PipelineStatus.
        """

        if isinstance(
            raw_status,
            PipelineStatus,
        ):
            return raw_status

        value = str(
            raw_status
        ).strip().lower()

        status_map = {
            "created": PipelineStatus.CREATED,
            "started": PipelineStatus.RUNNING,
            "running": PipelineStatus.RUNNING,
            "completed": PipelineStatus.SUCCESS,
            "success": PipelineStatus.SUCCESS,
            "failed": PipelineStatus.FAILED,
            "rolling_back": PipelineStatus.ROLLING_BACK,
            "rolled_back": PipelineStatus.ROLLED_BACK,
        }

        if value in status_map:

            return status_map[value]

        try:

            return PipelineStatus(
                value
            )

        except ValueError:

            return PipelineStatus.FAILED

    # ========================================================================
    # LEAKAGE FILTER
    # ========================================================================

    @staticmethod
    def _apply_leakage_filter(
        df: pd.DataFrame,
        leakage_report: Any,
        target: str,
    ) -> pd.DataFrame:
        """
        Remove features explicitly identified as risky by leakage detection.

        The target itself is never removed.
        """

        risky = set(
            getattr(
                leakage_report,
                "risky_features",
                (),
            )
        )

        cols_to_drop = [
            column
            for column in risky
            if column in df.columns
            and column != target
        ]

        if cols_to_drop:

            return df.drop(
                columns=cols_to_drop
            )

        return df

    # ========================================================================
    # ARTIFACT BUILDER
    # ========================================================================

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
        """
        Build ModelArtifact using the already fitted model pipeline.

        No second model training pass is performed.
        """

        from core.inference.engine import (
            ModelArtifact,
        )

        best_model_name = getattr(
            training_result,
            "best_model_name",
            None,
        )

        if not best_model_name:

            return None

        evaluations = getattr(
            training_result,
            "evaluations",
            (),
        )

        best_eval = next(
            (
                evaluation
                for evaluation in evaluations
                if (
                    evaluation.model_name
                    == best_model_name
                )
            ),
            None,
        )

        if best_eval is None:

            return None

        fitted_pipeline = (
            self.trainer.get_fitted_pipeline(
                best_model_name
            )
        )

        return ModelArtifact(
            model_name=best_model_name,
            task_type=task_type,
            execution_id=execution_id,
            pipeline=fitted_pipeline,
            feature_columns=feature_columns,
            target_column=target,
            metrics=best_eval.metrics,
            validation_strategy=(
                val_strategy.strategy
            ),
            dataset_fingerprint=fingerprint,
            checkpoint_id=checkpoint_id,
        )

    # ========================================================================
    # FAILURE RESULT
    # ========================================================================

    def _fail(
        self,
        **kwargs: Any,
    ) -> OrchestratorResult:
        """
        Build a safe failed OrchestratorResult and persist the failure.
        """

        started_at = kwargs.pop(
            "started_at",
            _utc_now(),
        )

        warnings = kwargs.pop(
            "warnings",
            [],
        )

        execution_id = kwargs.get(
            "execution_id",
            str(uuid.uuid4()),
        )

        dataset_path = kwargs.get(
            "dataset_path",
            "unknown",
        )

        fingerprint = kwargs.get(
            "fingerprint",
            kwargs.get(
                "dataset_fingerprint",
                "",
            ),
        )

        message = kwargs.get(
            "message",
            "Pipeline failed.",
        )

        # --------------------------------------------------------------
        # Persist failure
        # --------------------------------------------------------------

        self._persist_execution_completion(
            execution_id=execution_id,
            success=False,
            message=message,
            result={
                "error": message,
                "dataset_path": dataset_path,
                "dataset_fingerprint": fingerprint,
            },
        )

        # --------------------------------------------------------------
        # Normalize dataclass field name
        # --------------------------------------------------------------

        allowed_fields = (
            OrchestratorResult
            .__dataclass_fields__
        )

        payload = {}

        for key, value in kwargs.items():

            if key == "fingerprint":

                key = "dataset_fingerprint"

            if key in allowed_fields:

                payload[key] = value

        payload.setdefault(
            "execution_id",
            execution_id,
        )

        payload.setdefault(
            "dataset_path",
            dataset_path,
        )

        payload.setdefault(
            "dataset_fingerprint",
            fingerprint,
        )

        payload["success"] = False

        payload["warnings"] = tuple(
            warnings
        )

        payload["started_at"] = (
            started_at
        )

        payload["completed_at"] = (
            _utc_now()
        )

        return OrchestratorResult(
            **payload
        )

    # ========================================================================
    # DATABASE PERSISTENCE
    # ========================================================================

    def _persist_execution_completion(
        self,
        *,
        execution_id: str,
        success: bool,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> None:
        """
        Persist final execution state.

        Persistence errors are intentionally swallowed here because database
        failure must not replace the actual ML pipeline result.
        """

        try:

            self.execution_repository.complete_execution(
                execution_id=execution_id,
                success=success,
                message=message,
                result=result,
                status=status,
            )

        except Exception:
            pass

    def _persist_fault(
        self,
        *,
        execution_id: str,
        fault_type: str,
        severity: str = "unknown",
        component: str | None = None,
        message: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """
        Persist a detected fault without allowing persistence failure to
        break the self-healing chain.
        """

        try:

            self.execution_repository.record_fault(
                execution_id=execution_id,
                fault_type=fault_type,
                severity=severity,
                component=component,
                message=message,
                evidence=evidence,
            )

        except Exception:
            pass

    def _persist_recovery_result(
        self,
        *,
        execution_id: str,
        decision: Any,
        recovery_result: Any,
    ) -> None:
        """
        Persist recovery decision/outcome in the recovery_events table.
        """

        try:

            decision_value = getattr(
                decision,
                "decision",
                None,
            )

            if decision_value is None:

                decision_value = getattr(
                    decision,
                    "action",
                    None,
                )

            if decision_value is None:

                decision_value = type(
                    decision
                ).__name__

            action = getattr(
                decision,
                "action",
                None,
            )

            if hasattr(
                action,
                "value",
            ):
                action = action.value

            status = getattr(
                recovery_result,
                "status",
                None,
            )

            if hasattr(
                status,
                "value",
            ):
                status = status.value

            if status is None:

                status = (
                    "completed"
                    if getattr(
                        recovery_result,
                        "success",
                        False,
                    )
                    else "failed"
                )

            reason = getattr(
                decision,
                "reason",
                None,
            )

            evidence: dict[str, Any] = {
                "decision_type": type(
                    decision
                ).__name__,
                "recovery_type": type(
                    recovery_result
                ).__name__,
            }

            # ----------------------------------------------------------
            # Add serializable details where available
            # ----------------------------------------------------------

            for source, prefix in (
                (
                    decision,
                    "decision",
                ),
                (
                    recovery_result,
                    "recovery",
                ),
            ):

                to_dict = getattr(
                    source,
                    "to_dict",
                    None,
                )

                if callable(to_dict):

                    try:

                        evidence[
                            prefix
                        ] = to_dict()

                    except Exception:
                        pass

            self.execution_repository.record_recovery(
                execution_id=execution_id,
                decision=str(
                    decision_value
                ),
                status=str(
                    status
                ),
                action=(
                    str(action)
                    if action is not None
                    else None
                ),
                reason=(
                    str(reason)
                    if reason is not None
                    else None
                ),
                evidence=evidence,
            )

        except Exception:
            pass


# ============================================================================
# Public exports
# ============================================================================


__all__ = [
    "AyaskXOrchestrator",
    "OrchestratorResult",
]
