"""
core/self_healing/orchestrator.py
-----------------------------------
SelfHealingOrchestrator — the end-to-end self-healing entry point.

Phase M: END-TO-END SELF-HEALING ORCHESTRATOR

Implements the complete deterministic self-healing chain:

  1.  DETECT          — FaultDetector.detect()
  2.  LOCALIZE        — FaultLocalizer.localize()
  3.  DIAGNOSE        — RootCauseAnalyzer.analyze()
  4.  DECIDE          — RecoveryDecisionEngine.decide()
  5.  PLAN            — RepairPlanner.plan()
  6.  SAFETY_CHECK    — approve / reject plan based on risk + approval policy
  7.  SANDBOX         — SandboxExecutor.execute_plan()
  8.  VALIDATE        — RecoveryValidator (checkpoint or node execution)
  9.  RESUME / ROLLBACK / ESCALATE

Safety guarantees
-----------------
- Does NOT bypass FaultDetector, FaultLocalizer, RecoveryDecisionEngine,
  RecoveryExecutor, RecoveryValidator, ArtifactIntegrityChecker,
  SecurityRecoveryManager, or CheckpointManager.
- Reads existing module implementations; duplicates zero logic.
- Does NOT automatically execute plans that require human approval unless
  auto_approve_low_risk=True (only for LOW-risk plans without MANUAL_REVIEW).
- MANUAL_REVIEW and QUARANTINE decisions are never auto-executed.
- All state transitions emit structured NodeEvent records.
- No filesystem destructive actions (no delete/move/overwrite).
- Every SelfHealingResult is immutable and fully serializable.

Design decisions
----------------
- CheckpointManager is required at construction (same one the pipeline uses).
- RecoveryExecutor is constructed internally but callers can inject one.
- SandboxExecutor is stateless; constructed fresh per call unless injected.
- The orchestrator is stateless between calls — safe to reuse.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.analysis.root_cause import RootCauseAnalyzer
from core.fault.detector import FaultDetector
from core.fault.localizer import FaultLocalizer
from core.observability.events import NodeEvent
from core.recovery.decision import RecoveryActionType, RecoveryDecisionEngine
from core.recovery.executor import RecoveryExecutor
from core.recovery.models import RecoveryStatus, RecoveryResult
from core.recovery.validator import RecoveryValidator
from core.repair.planner import RepairPlanner, RiskLevel
from core.repair.sandbox import SandboxExecutor, SandboxStatus
from core.self_healing.models import (
    SelfHealingResult,
    SelfHealingStatus,
    SelfHealingTimestamps,
)

if TYPE_CHECKING:
    from core.fault.models import FaultLocalization, FaultReport
    from core.pipeline.checkpoints.manager import Checkpoint, CheckpointManager
    from core.pipeline.executor import PipelineExecution
    from core.recovery.decision import RecoveryDecision
    from core.repair.planner import RepairPlan
    from core.repair.sandbox import SandboxResult


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# SelfHealingOrchestrator
# ---------------------------------------------------------------------------


class SelfHealingOrchestrator:
    """
    Central orchestrator for AyaskX deterministic self-healing.

    Parameters
    ----------
    checkpoint_manager     : CheckpointManager — the same one the pipeline uses.
    auto_approve_low_risk  : bool — if True, plans with risk_level==LOW and
                             no MANUAL_REVIEW step are executed automatically.
                             Default: False (conservative / always requires
                             human approval for real production use).
    pipeline_id            : str — label used in emitted NodeEvents.
    recovery_executor      : RecoveryExecutor, optional — injected for testing.
    sandbox_executor       : SandboxExecutor, optional — injected for testing.

    Usage
    -----
    orchestrator = SelfHealingOrchestrator(checkpoint_manager=ckpt_mgr)
    result = orchestrator.handle_failure(execution, events=events)
    """

    def __init__(
        self,
        checkpoint_manager: "CheckpointManager",
        *,
        auto_approve_low_risk: bool = False,
        pipeline_id: str = "self_healing",
        recovery_executor: RecoveryExecutor | None = None,
        sandbox_executor: SandboxExecutor | None = None,
    ) -> None:
        self._checkpoint_manager = checkpoint_manager
        self._auto_approve_low_risk = auto_approve_low_risk
        self._pipeline_id = pipeline_id

        self._detector = FaultDetector()
        self._localizer = FaultLocalizer()
        self._root_cause_analyzer = RootCauseAnalyzer()
        self._decision_engine = RecoveryDecisionEngine()
        self._repair_planner = RepairPlanner()
        self._validator = RecoveryValidator()

        self._recovery_executor = recovery_executor or RecoveryExecutor(
            checkpoint_manager=checkpoint_manager,
            validator=self._validator,
            pipeline_id=pipeline_id,
        )
        self._sandbox_executor = sandbox_executor or SandboxExecutor()

        self._events: list[NodeEvent] = []

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def handle_failure(
        self,
        execution: "PipelineExecution",
        *,
        events: tuple["NodeEvent", ...] = (),
        last_known_good_checkpoint: "Checkpoint | None" = None,
    ) -> SelfHealingResult:
        """
        Run the complete self-healing chain for a failed pipeline execution.

        Parameters
        ----------
        execution                  : completed (FAILED or SUCCESS) pipeline run
        events                     : observability events from the pipeline run
        last_known_good_checkpoint : Checkpoint to use for rollback/rerun.
                                     If None, the CheckpointManager is queried
                                     automatically.

        Returns
        -------
        SelfHealingResult — always. Never raises to the caller.
        """
        self._events = []
        ts_started = _utc_now()
        audit_refs: list[str] = []
        errors: list[str] = []

        self._emit(
            execution_id=execution.execution_id,
            event_type="self_healing_started",
            status="running",
            message="SelfHealingOrchestrator started.",
            metadata={"execution_id": execution.execution_id},
        )

        # ── Resolve last-known-good checkpoint ───────────────────────────────

        if last_known_good_checkpoint is None:
            last_known_good_checkpoint = (
                self._checkpoint_manager.last_known_good(
                    execution_id=execution.execution_id
                )
            )

        # ── STEP 1: DETECT ───────────────────────────────────────────────────

        try:
            fault = self._detector.detect(execution)
            ts_detected = _utc_now()
        except Exception as exc:
            errors.append(f"FaultDetector raised: {type(exc).__name__}: {exc}")
            return self._error_result(
                execution.execution_id,
                errors,
                ts_started,
                "FaultDetector raised an unexpected exception.",
            )

        self._emit(
            execution_id=execution.execution_id,
            event_type="fault_detected",
            status="running",
            message=(
                f"Fault detection: detected={fault.detected} "
                f"type={fault.fault_type.value}"
            ),
            metadata=fault.to_dict(),
        )

        # No fault → nothing to heal
        if not fault.detected:
            self._emit(
                execution_id=execution.execution_id,
                event_type="self_healing_completed",
                status="success",
                message="No fault detected. Pipeline is healthy.",
            )
            return SelfHealingResult(
                execution_id=execution.execution_id,
                success=True,
                final_status=SelfHealingStatus.NO_FAULT,
                fault_report=fault.to_dict(),
                timestamps=SelfHealingTimestamps(
                    started_at=ts_started,
                    detected_at=ts_detected,
                    completed_at=_utc_now(),
                ),
                observability_events=tuple(self._events),
            )

        # ── STEP 2: LOCALIZE ─────────────────────────────────────────────────

        try:
            localization = self._localizer.localize(
                execution, fault, events=events
            )
            ts_localized = _utc_now()
        except Exception as exc:
            errors.append(f"FaultLocalizer raised: {type(exc).__name__}: {exc}")
            return self._error_result(
                execution.execution_id,
                errors,
                ts_started,
                "FaultLocalizer raised an unexpected exception.",
                fault_report=fault.to_dict(),
            )

        self._emit(
            execution_id=execution.execution_id,
            event_type="fault_localized",
            status="running",
            message=(
                f"Localized root node: {localization.probable_root_node} "
                f"(confidence={localization.confidence:.2f})"
            ),
            metadata=localization.to_dict(),
        )

        # ── STEP 3: DIAGNOSE (Root Cause Analysis) ───────────────────────────

        try:
            root_cause = self._root_cause_analyzer.analyze(
                execution, fault, localization, events=events
            )
            ts_diagnosed = _utc_now()
        except Exception as exc:
            errors.append(f"RootCauseAnalyzer raised: {type(exc).__name__}: {exc}")
            return self._error_result(
                execution.execution_id,
                errors,
                ts_started,
                "RootCauseAnalyzer raised an unexpected exception.",
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
            )

        self._emit(
            execution_id=execution.execution_id,
            event_type="root_cause_analyzed",
            status="running",
            message=(
                f"Root cause: {root_cause.primary_fault_type} "
                f"(confidence={root_cause.confidence:.2f}) "
                f"root_node={root_cause.root_node}"
            ),
            metadata={
                "primary_fault_type": root_cause.primary_fault_type,
                "confidence": root_cause.confidence,
                "root_node": root_cause.root_node,
            },
        )

        # ── STEP 4: DECIDE ───────────────────────────────────────────────────

        try:
            decision = self._decision_engine.decide(
                execution,
                fault,
                localization,
                last_known_good_checkpoint=last_known_good_checkpoint,
            )
            ts_decided = _utc_now()
        except Exception as exc:
            errors.append(
                f"RecoveryDecisionEngine raised: {type(exc).__name__}: {exc}"
            )
            return self._error_result(
                execution.execution_id,
                errors,
                ts_started,
                "RecoveryDecisionEngine raised an unexpected exception.",
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
            )

        self._emit(
            execution_id=execution.execution_id,
            event_type="recovery_decision_made",
            status="running",
            message=(
                f"Recovery decision: {decision.action.value} "
                f"requires_approval={decision.requires_approval}"
            ),
            metadata=decision.to_dict(),
        )

        # MANUAL_REVIEW / ABORT from the decision engine → no automated path
        if decision.action == RecoveryActionType.MANUAL_REVIEW:
            self._emit(
                execution_id=execution.execution_id,
                event_type="manual_review_required",
                status="pending",
                message=f"Manual review required: {decision.reason}",
            )
            return SelfHealingResult(
                execution_id=execution.execution_id,
                success=False,
                final_status=SelfHealingStatus.MANUAL_REVIEW,
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
                recovery_decision=decision.to_dict(),
                errors=tuple(errors),
                timestamps=SelfHealingTimestamps(
                    started_at=ts_started,
                    detected_at=ts_detected,
                    localized_at=ts_localized,
                    diagnosed_at=ts_diagnosed,
                    completed_at=_utc_now(),
                ),
                observability_events=tuple(self._events),
            )

        if decision.action == RecoveryActionType.ABORT:
            self._emit(
                execution_id=execution.execution_id,
                event_type="self_healing_aborted",
                status="aborted",
                message=f"Recovery aborted: {decision.reason}",
            )
            return SelfHealingResult(
                execution_id=execution.execution_id,
                success=False,
                final_status=SelfHealingStatus.ABORTED,
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
                recovery_decision=decision.to_dict(),
                errors=tuple(errors),
                timestamps=SelfHealingTimestamps(
                    started_at=ts_started,
                    detected_at=ts_detected,
                    localized_at=ts_localized,
                    diagnosed_at=ts_diagnosed,
                    completed_at=_utc_now(),
                ),
                observability_events=tuple(self._events),
            )

        if decision.action == RecoveryActionType.QUARANTINE:
            self._emit(
                execution_id=execution.execution_id,
                event_type="self_healing_quarantined",
                status="quarantined",
                message=f"Artifact quarantined: {decision.reason}",
            )
            return SelfHealingResult(
                execution_id=execution.execution_id,
                success=False,
                final_status=SelfHealingStatus.QUARANTINED,
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
                recovery_decision=decision.to_dict(),
                errors=tuple(errors),
                timestamps=SelfHealingTimestamps(
                    started_at=ts_started,
                    detected_at=ts_detected,
                    localized_at=ts_localized,
                    diagnosed_at=ts_diagnosed,
                    completed_at=_utc_now(),
                ),
                observability_events=tuple(self._events),
            )

        # ── STEP 5: PLAN ─────────────────────────────────────────────────────

        lkg_checkpoint_id: str | None = getattr(
            last_known_good_checkpoint, "checkpoint_id", None
        )

        try:
            repair_plan = self._repair_planner.plan(
                root_cause,
                last_known_good_checkpoint=lkg_checkpoint_id,
            )
            ts_planned = _utc_now()
        except Exception as exc:
            errors.append(f"RepairPlanner raised: {type(exc).__name__}: {exc}")
            return self._error_result(
                execution.execution_id,
                errors,
                ts_started,
                "RepairPlanner raised an unexpected exception.",
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
                recovery_decision=decision.to_dict(),
            )

        self._emit(
            execution_id=execution.execution_id,
            event_type="repair_plan_created",
            status="running",
            message=(
                f"Repair plan: {repair_plan.step_count} step(s) "
                f"category={repair_plan.hypothesis_category} "
                f"requires_approval={repair_plan.requires_approval}"
            ),
            metadata={
                "step_count": repair_plan.step_count,
                "category": repair_plan.hypothesis_category,
                "requires_approval": repair_plan.requires_approval,
            },
        )

        # ── STEP 6: SAFETY CHECK ─────────────────────────────────────────────

        # Plans with MANUAL_REVIEW steps always require human authorization.
        has_manual_step = any(
            s.action_type == "MANUAL_REVIEW" for s in repair_plan.steps
        )
        plan_is_auto_safe = (
            not repair_plan.requires_approval
            and not has_manual_step
        ) or (
            self._auto_approve_low_risk
            and not has_manual_step
            and all(
                s.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
                for s in repair_plan.steps
            )
        )

        self._emit(
            execution_id=execution.execution_id,
            event_type="repair_safety_checked",
            status="running",
            message=(
                f"Safety check: auto_safe={plan_is_auto_safe} "
                f"requires_approval={repair_plan.requires_approval}"
            ),
            metadata={
                "auto_safe": plan_is_auto_safe,
                "has_manual_step": has_manual_step,
                "requires_approval": repair_plan.requires_approval,
            },
        )

        if not plan_is_auto_safe:
            # Plan requires human authorization — cannot auto-execute
            self._emit(
                execution_id=execution.execution_id,
                event_type="manual_review_required",
                status="pending",
                message=(
                    "Repair plan requires human approval before execution. "
                    f"Step count={repair_plan.step_count} "
                    f"category={repair_plan.hypothesis_category}"
                ),
            )
            return SelfHealingResult(
                execution_id=execution.execution_id,
                success=False,
                final_status=SelfHealingStatus.MANUAL_REVIEW,
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
                recovery_decision=decision.to_dict(),
                repair_plan=repair_plan.to_dict(),
                errors=tuple(errors),
                timestamps=SelfHealingTimestamps(
                    started_at=ts_started,
                    detected_at=ts_detected,
                    localized_at=ts_localized,
                    diagnosed_at=ts_diagnosed,
                    planned_at=ts_planned,
                    completed_at=_utc_now(),
                ),
                observability_events=tuple(self._events),
            )

        # ── STEP 7: SANDBOX EXECUTION ────────────────────────────────────────

        ts_sandbox_started = _utc_now()
        self._emit(
            execution_id=execution.execution_id,
            event_type="repair_sandbox_started",
            status="running",
            message=(
                f"Sandbox execution started. "
                f"Backend: {self._sandbox_executor._backend.execution_mode} "
                f"(no OS-level isolation for in_process backend). "
                f"Steps: {repair_plan.step_count}"
            ),
        )

        try:
            sandbox_result = self._sandbox_executor.execute_plan(repair_plan)
            ts_sandbox_completed = _utc_now()
        except Exception as exc:
            errors.append(
                f"SandboxExecutor raised: {type(exc).__name__}: {exc}"
            )
            return self._error_result(
                execution.execution_id,
                errors,
                ts_started,
                "SandboxExecutor raised an unexpected exception.",
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
                recovery_decision=decision.to_dict(),
                repair_plan=repair_plan.to_dict(),
            )

        self._emit(
            execution_id=execution.execution_id,
            event_type="repair_sandbox_completed",
            status="success" if sandbox_result.success else "failed",
            message=(
                f"Sandbox completed: success={sandbox_result.success} "
                f"{sandbox_result.steps_succeeded}/{repair_plan.step_count} steps OK"
            ),
            metadata={
                "success": sandbox_result.success,
                "steps_succeeded": sandbox_result.steps_succeeded,
                "steps_failed": sandbox_result.steps_failed,
                "execution_mode": sandbox_result.execution_mode,
            },
        )

        # ── STEP 8: VALIDATION ───────────────────────────────────────────────

        ts_validated = _utc_now()
        self._emit(
            execution_id=execution.execution_id,
            event_type="repair_validation_started",
            status="running",
            message="Validating repair outcome.",
        )

        # Primary validation: did the sandbox succeed?
        sandbox_validation_passed = sandbox_result.success

        if sandbox_validation_passed:
            # Additional checkpoint validation if we have a rollback checkpoint
            ckpt_validation = None
            if last_known_good_checkpoint is not None and (
                decision.action in (
                    RecoveryActionType.ROLLBACK,
                    RecoveryActionType.RERUN_FROM_NODE,
                )
            ):
                ckpt_validation = self._validator.validate_checkpoint(
                    last_known_good_checkpoint
                )
                if not ckpt_validation.passed:
                    sandbox_validation_passed = False
                    self._emit(
                        execution_id=execution.execution_id,
                        event_type="repair_validation_failed",
                        status="failed",
                        message=(
                            "Checkpoint validation failed after sandbox: "
                            f"{ckpt_validation.message}"
                        ),
                    )

        if sandbox_validation_passed:
            # ── STEP 9a: RESUME ──────────────────────────────────────────────
            self._emit(
                execution_id=execution.execution_id,
                event_type="repair_validation_passed",
                status="success",
                message="Repair validated successfully. Pipeline can resume.",
            )
            self._emit(
                execution_id=execution.execution_id,
                event_type="pipeline_resumed",
                status="success",
                message=(
                    f"Pipeline resumed from node: {repair_plan.root_node or 'unknown'}"
                ),
            )
            return SelfHealingResult(
                execution_id=execution.execution_id,
                success=True,
                final_status=SelfHealingStatus.RESUMED,
                fault_report=fault.to_dict(),
                localization=localization.to_dict(),
                root_cause=root_cause.to_dict(),
                recovery_decision=decision.to_dict(),
                repair_plan=repair_plan.to_dict(),
                sandbox_result=sandbox_result.to_dict(),
                validation_result=(
                    ckpt_validation.to_dict()
                    if "ckpt_validation" in locals() and ckpt_validation is not None
                    else None
                ),
                resumed_from_node=repair_plan.root_node,
                audit_references=tuple(audit_refs),
                errors=tuple(errors),
                timestamps=SelfHealingTimestamps(
                    started_at=ts_started,
                    detected_at=ts_detected,
                    localized_at=ts_localized,
                    diagnosed_at=ts_diagnosed,
                    planned_at=ts_planned,
                    sandbox_started_at=ts_sandbox_started,
                    sandbox_completed_at=ts_sandbox_completed,
                    validated_at=ts_validated,
                    completed_at=_utc_now(),
                ),
                observability_events=tuple(self._events),
            )

        # ── STEP 9b: Sandbox failed or validation failed → ROLLBACK ──────────

        self._emit(
            execution_id=execution.execution_id,
            event_type="pipeline_rollback_started",
            status="running",
            message=(
                "Sandbox repair did not validate. "
                "Attempting rollback to last known-good checkpoint."
            ),
        )

        rolled_back_to: str | None = None
        rollback_result: RecoveryResult | None = None

        if last_known_good_checkpoint is not None:
            # Verify checkpoint trust before using it
            trust_check = self._validator.validate_checkpoint(
                last_known_good_checkpoint
            )
            if trust_check.passed:
                try:
                    from core.recovery.decision import RecoveryDecision
                    rollback_decision = RecoveryDecision(
                        execution_id=execution.execution_id,
                        action=RecoveryActionType.ROLLBACK,
                        requires_approval=False,  # triggered by failed repair
                        reason=(
                            "Sandbox repair failed validation. "
                            "Rolling back to last-known-good checkpoint."
                        ),
                        checkpoint_id=lkg_checkpoint_id,
                    )
                    rollback_result = self._recovery_executor.execute(
                        rollback_decision
                    )
                    if rollback_result.success:
                        rolled_back_to = lkg_checkpoint_id
                        self._emit(
                            execution_id=execution.execution_id,
                            event_type="pipeline_rollback_completed",
                            status="success",
                            message=(
                                f"Rollback to checkpoint '{lkg_checkpoint_id}' "
                                "completed."
                            ),
                        )
                    else:
                        errors.append(
                            f"Rollback failed: {rollback_result.message}"
                        )
                except Exception as exc:
                    errors.append(
                        f"Rollback raised: {type(exc).__name__}: {exc}"
                    )
            else:
                # Checkpoint not trusted — escalate
                errors.append(
                    f"Last-known-good checkpoint failed trust validation: "
                    f"{trust_check.message}"
                )
                self._emit(
                    execution_id=execution.execution_id,
                    event_type="manual_review_required",
                    status="pending",
                    message=(
                        "Rollback checkpoint failed trust validation. "
                        "Manual review required."
                    ),
                )
                return SelfHealingResult(
                    execution_id=execution.execution_id,
                    success=False,
                    final_status=SelfHealingStatus.MANUAL_REVIEW,
                    fault_report=fault.to_dict(),
                    localization=localization.to_dict(),
                    root_cause=root_cause.to_dict(),
                    recovery_decision=decision.to_dict(),
                    repair_plan=repair_plan.to_dict(),
                    sandbox_result=sandbox_result.to_dict(),
                    validation_result=trust_check.to_dict(),
                    errors=tuple(errors),
                    timestamps=SelfHealingTimestamps(
                        started_at=ts_started,
                        detected_at=ts_detected,
                        localized_at=ts_localized,
                        diagnosed_at=ts_diagnosed,
                        planned_at=ts_planned,
                        sandbox_started_at=ts_sandbox_started,
                        sandbox_completed_at=ts_sandbox_completed,
                        validated_at=ts_validated,
                        completed_at=_utc_now(),
                    ),
                    observability_events=tuple(self._events),
                )
        else:
            errors.append(
                "No last-known-good checkpoint available for rollback."
            )

        final_status = (
            SelfHealingStatus.ROLLED_BACK
            if rolled_back_to is not None
            else SelfHealingStatus.FAILED
        )
        self._emit(
            execution_id=execution.execution_id,
            event_type=(
                "pipeline_rollback_completed"
                if rolled_back_to
                else "self_healing_aborted"
            ),
            status="success" if rolled_back_to else "failed",
            message=(
                f"Final status: {final_status.value}. "
                f"Rolled back to: {rolled_back_to or 'N/A'}"
            ),
        )

        return SelfHealingResult(
            execution_id=execution.execution_id,
            success=False,
            final_status=final_status,
            fault_report=fault.to_dict(),
            localization=localization.to_dict(),
            root_cause=root_cause.to_dict(),
            recovery_decision=decision.to_dict(),
            repair_plan=repair_plan.to_dict(),
            sandbox_result=sandbox_result.to_dict(),
            recovery_result=(
                rollback_result.to_dict() if rollback_result is not None else None
            ),
            rolled_back_to_checkpoint=rolled_back_to,
            audit_references=tuple(audit_refs),
            errors=tuple(errors),
            timestamps=SelfHealingTimestamps(
                started_at=ts_started,
                detected_at=ts_detected,
                localized_at=ts_localized,
                diagnosed_at=ts_diagnosed,
                planned_at=ts_planned,
                sandbox_started_at=ts_sandbox_started,
                sandbox_completed_at=ts_sandbox_completed,
                validated_at=ts_validated,
                completed_at=_utc_now(),
            ),
            observability_events=tuple(self._events),
        )

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def events(self) -> tuple[NodeEvent, ...]:
        """All structured observability events from the last handle_failure()."""
        return tuple(self._events)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _emit(
        self,
        *,
        execution_id: str,
        event_type: str,
        status: str,
        message: str,
        metadata: dict | None = None,
    ) -> None:
        """Emit a structured NodeEvent to the internal event log."""
        self._events.append(
            NodeEvent(
                execution_id=execution_id,
                pipeline_id=self._pipeline_id,
                node_id="self_healing",
                event_type=event_type,
                status=status,
                message=message,
                metadata=metadata or {},
            )
        )

    def _error_result(
        self,
        execution_id: str,
        errors: list[str],
        ts_started: datetime,
        message: str,
        *,
        fault_report: dict | None = None,
        localization: dict | None = None,
        root_cause: dict | None = None,
        recovery_decision: dict | None = None,
        repair_plan: dict | None = None,
    ) -> SelfHealingResult:
        """Produce a FAILED SelfHealingResult for unexpected exceptions."""
        self._emit(
            execution_id=execution_id,
            event_type="self_healing_aborted",
            status="failed",
            message=message,
            metadata={"errors": errors},
        )
        return SelfHealingResult(
            execution_id=execution_id,
            success=False,
            final_status=SelfHealingStatus.FAILED,
            fault_report=fault_report,
            localization=localization,
            root_cause=root_cause,
            recovery_decision=recovery_decision,
            repair_plan=repair_plan,
            errors=tuple(errors),
            timestamps=SelfHealingTimestamps(
                started_at=ts_started,
                completed_at=_utc_now(),
            ),
            observability_events=tuple(self._events),
        )
