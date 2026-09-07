"""
core/recovery/executor.py
-------------------------
Checkpoint-aware recovery executor for AyaskX self-healing foundation.

Phase: CHECKPOINT-AWARE RECOVERY EXECUTION

This module EXECUTES a RecoveryDecision produced by RecoveryDecisionEngine.
It is deliberately separate from the decision engine, which remains a pure
policy engine with zero side effects.

Architecture position:

    RecoveryDecisionEngine (pure policy)
            ↓
       RecoveryDecision (intent, immutable)
            ↓
       RecoveryExecutor  ← this file
            ↓
       RecoveryValidator (validation gate)
            ↓
       RecoveryResult (outcome, immutable)

Safety model:
- NEVER blindly executes recovery.
- NEVER invents a checkpoint.
- NEVER continues after a failed validation gate.
- NEVER recurses or retries beyond max_attempts (default: 1).
- MANUAL_REVIEW and QUARANTINE are never executed automatically.
- All outcomes are recorded in an immutable RecoveryResult.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Iterable

from core.observability.events import NodeEvent
from core.recovery.decision import RecoveryActionType, RecoveryDecision
from core.recovery.errors import (
    CheckpointNotFoundError,
    CheckpointValidationError,
    NodeRerunError,
    UnsafeRecoveryError,
)
from core.recovery.models import RecoveryResult, RecoveryStatus, ValidationResult
from core.recovery.validator import RecoveryValidator

if TYPE_CHECKING:
    from core.pipeline.checkpoints.manager import Checkpoint, CheckpointManager


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ArtifactQuarantine abstraction
# ---------------------------------------------------------------------------


class ArtifactQuarantine:
    """
    Abstraction for artifact quarantine actions.

    For this phase this records the quarantine request as a structured
    event rather than performing destructive filesystem or security operations.
    Future implementation will integrate with a SecurityRecoveryManager.

    Do NOT:
    - Delete files
    - Revoke credentials
    - Modify production infrastructure
    """

    def quarantine(
        self,
        *,
        execution_id: str,
        node_id: str | None,
        checkpoint_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        """
        Record a quarantine request.

        Returns a structured dict that can be persisted for audit.
        This is NOT destructive in this phase.
        """
        return {
            "quarantine_requested": True,
            "execution_id": execution_id,
            "node_id": node_id,
            "checkpoint_id": checkpoint_id,
            "reason": reason,
            "timestamp": _utc_now().isoformat(),
        }


# ---------------------------------------------------------------------------
# RecoveryExecutor
# ---------------------------------------------------------------------------


class RecoveryExecutor:
    """
    Executes a RecoveryDecision safely and produces an auditable RecoveryResult.

    Supported actions:
        RETRY           — re-execute the pipeline via the supplied callable
        RERUN_FROM_NODE — restore upstream checkpoint, rerun from target node
        ROLLBACK        — restore last-known-good checkpoint, no rerun
        ABORT           — return structured abort result (no execution)
        MANUAL_REVIEW   — return pending-review result (no execution)
        QUARANTINE      — record quarantine, return structured result (no exec)

    Parameters
    ----------
    checkpoint_manager : CheckpointManager
        The EXISTING pipeline checkpoint manager. This executor uses it to
        look up and restore checkpoints. It never creates an alternative.
    validator : RecoveryValidator, optional
        Validation gate applied after node rerun or rollback.
        Defaults to a new RecoveryValidator().
    quarantine : ArtifactQuarantine, optional
        Quarantine abstraction. Defaults to a new ArtifactQuarantine().
    pipeline_id : str
        Used for NodeEvent construction.
    max_attempts : int
        Maximum number of node rerun attempts. Default: 1.
        There are NO infinite retries.
    """

    def __init__(
        self,
        checkpoint_manager: "CheckpointManager",
        *,
        validator: RecoveryValidator | None = None,
        quarantine: ArtifactQuarantine | None = None,
        pipeline_id: str = "recovery",
        max_attempts: int = 1,
    ) -> None:

        self.checkpoint_manager = checkpoint_manager
        self.validator = validator or RecoveryValidator()
        self.quarantine = quarantine or ArtifactQuarantine()
        self.pipeline_id = pipeline_id
        self.max_attempts = max_attempts

        self._events: list[NodeEvent] = []

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def execute(
        self,
        decision: RecoveryDecision,
        *,
        nodes: Iterable[Any] | None = None,
        pipeline_callable: Callable[[], Any] | None = None,
    ) -> RecoveryResult:
        """
        Execute the prescribed RecoveryDecision.

        Parameters
        ----------
        decision          : RecoveryDecision produced by RecoveryDecisionEngine
        nodes             : ordered node list for RERUN_FROM_NODE (required for
                            that action; ignored for ROLLBACK/ABORT/…)
        pipeline_callable : zero-arg callable for RETRY (re-runs full pipeline)

        Returns
        -------
        RecoveryResult — always. Never raises to the caller.
        """

        self._events.clear()

        self._emit(
            execution_id=decision.execution_id,
            node_id=decision.target_node or "pipeline",
            event_type="recovery_started",
            status="running",
            message=f"Starting recovery action: {decision.action.value}",
            metadata={
                "action": decision.action.value,
                "checkpoint_id": decision.checkpoint_id,
                "target_node": decision.target_node,
            },
        )

        try:
            if decision.action == RecoveryActionType.RETRY:
                return self._execute_retry(decision, pipeline_callable)

            elif decision.action == RecoveryActionType.RERUN_FROM_NODE:
                return self._execute_rerun(decision, nodes)

            elif decision.action == RecoveryActionType.ROLLBACK:
                return self._execute_rollback(decision)

            elif decision.action == RecoveryActionType.ABORT:
                return self._execute_abort(decision)

            elif decision.action == RecoveryActionType.MANUAL_REVIEW:
                return self._execute_manual_review(decision)

            elif decision.action == RecoveryActionType.QUARANTINE:
                return self._execute_quarantine(decision)

            else:
                # Unknown action — safe fallback
                return self._failed_result(
                    decision=decision,
                    status=RecoveryStatus.ABORTED,
                    message=f"Unknown recovery action: {decision.action.value}",
                )

        except (CheckpointNotFoundError, CheckpointValidationError) as exc:
            self._emit(
                execution_id=decision.execution_id,
                node_id=decision.target_node or "pipeline",
                event_type="recovery_failed",
                status="failed",
                message=str(exc),
            )
            return self._failed_result(
                decision=decision,
                status=RecoveryStatus.FAILED,
                message=str(exc),
                evidence=(f"checkpoint_error: {type(exc).__name__}: {exc}",),
            )

        except Exception as exc:
            self._emit(
                execution_id=decision.execution_id,
                node_id=decision.target_node or "pipeline",
                event_type="recovery_failed",
                status="failed",
                message=str(exc),
            )
            return self._failed_result(
                decision=decision,
                status=RecoveryStatus.FAILED,
                message=f"Unexpected recovery error: {exc}",
                evidence=(f"exception: {type(exc).__name__}: {exc}",),
            )

    @property
    def events(self) -> tuple[NodeEvent, ...]:
        """All structured observability events from the last execute() call."""
        return tuple(self._events)

    # -----------------------------------------------------------------------
    # RETRY
    # -----------------------------------------------------------------------

    def _execute_retry(
        self,
        decision: RecoveryDecision,
        pipeline_callable: Callable[[], Any] | None,
    ) -> RecoveryResult:
        """
        Re-execute the full pipeline via the supplied callable.

        If no callable is provided, return a structured result indicating
        that retry was requested but no executor was supplied.
        """

        self._emit(
            execution_id=decision.execution_id,
            node_id="pipeline",
            event_type="recovery_retry",
            status="running",
            message="Attempting pipeline retry.",
        )

        if pipeline_callable is None:
            # Retry requested but no callable provided — record as skipped
            self._emit(
                execution_id=decision.execution_id,
                node_id="pipeline",
                event_type="recovery_completed",
                status="skipped",
                message="Retry requested but no pipeline_callable was supplied.",
            )
            return RecoveryResult(
                execution_id=decision.execution_id,
                action=decision.action,
                status=RecoveryStatus.SKIPPED,
                success=False,
                recovered_from_checkpoint=None,
                resumed_from_node=None,
                message=(
                    "RETRY action requested but no pipeline_callable was "
                    "provided to RecoveryExecutor. Retry was not executed."
                ),
                evidence=("retry_skipped: no pipeline_callable supplied",),
                rollback_performed=False,
                validation_passed=False,
                events=tuple(self._events),
            )

        try:
            pipeline_callable()

        except Exception as exc:
            self._emit(
                execution_id=decision.execution_id,
                node_id="pipeline",
                event_type="recovery_failed",
                status="failed",
                message=f"Pipeline retry failed: {exc}",
            )
            return self._failed_result(
                decision=decision,
                status=RecoveryStatus.FAILED,
                message=f"Pipeline retry raised: {type(exc).__name__}: {exc}",
                evidence=(f"retry_exception: {exc}",),
            )

        self._emit(
            execution_id=decision.execution_id,
            node_id="pipeline",
            event_type="recovery_completed",
            status="success",
            message="Pipeline retry completed successfully.",
        )

        return RecoveryResult(
            execution_id=decision.execution_id,
            action=decision.action,
            status=RecoveryStatus.SUCCESS,
            success=True,
            recovered_from_checkpoint=None,
            resumed_from_node=None,
            message="Pipeline retry completed successfully.",
            evidence=("retry_executed_successfully",),
            rollback_performed=False,
            validation_passed=True,
            events=tuple(self._events),
        )

    # -----------------------------------------------------------------------
    # RERUN_FROM_NODE
    # -----------------------------------------------------------------------

    def _execute_rerun(
        self,
        decision: RecoveryDecision,
        nodes: Iterable[Any] | None,
    ) -> RecoveryResult:
        """
        Restore upstream checkpoint, then rerun from target_node onward.

        Steps:
          1. Verify and restore upstream checkpoint (if checkpoint_id provided).
          2. Find target_node in the node list.
          3. Execute nodes from target_node onward (limited by max_attempts).
          4. Validate each node's output.
          5. If a node fails → produce failed RecoveryResult.
          6. If all pass → produce success RecoveryResult.
        """

        target_node_id = decision.target_node
        checkpoint_id = decision.checkpoint_id

        # ── Step 1: verify/restore upstream checkpoint ──────────────────────

        restored_artifact: Any = None
        if checkpoint_id is not None:
            checkpoint = self._load_and_validate_checkpoint(
                checkpoint_id=checkpoint_id,
                execution_id=decision.execution_id,
            )
            # Restore the artifact (context) for the rerun
            try:
                restored_artifact = self.checkpoint_manager.restore(checkpoint_id)
            except Exception as exc:
                raise CheckpointNotFoundError(
                    f"Could not restore artifact from checkpoint "
                    f"'{checkpoint_id}': {exc}"
                )

        self._emit(
            execution_id=decision.execution_id,
            node_id=target_node_id or "unknown",
            event_type="recovery_rerun_started",
            status="running",
            message=(
                f"Rerun from node '{target_node_id}' "
                f"(upstream checkpoint: {checkpoint_id!r})."
            ),
            metadata={"checkpoint_id": checkpoint_id, "target_node": target_node_id},
        )

        # ── Step 2: find and execute nodes from target onward ────────────────

        if nodes is None:
            return self._failed_result(
                decision=decision,
                status=RecoveryStatus.FAILED,
                message=(
                    "RERUN_FROM_NODE requires a 'nodes' iterable but "
                    "none was provided to RecoveryExecutor.execute()."
                ),
            )

        node_list = list(nodes)
        found_target = False
        context: Any = restored_artifact
        rerun_node_id: str | None = None

        for node in node_list:
            node_id = self._node_id(node)

            if not found_target:
                if node_id == target_node_id:
                    found_target = True
                else:
                    continue  # skip nodes before the target

            # ── Execute this node ────────────────────────────────────────────
            rerun_node_id = rerun_node_id or node_id
            attempt = 0
            node_exec = None
            last_exc: Exception | None = None

            while attempt < self.max_attempts:
                attempt += 1
                self._emit(
                    execution_id=decision.execution_id,
                    node_id=node_id,
                    event_type="recovery_rerun_started",
                    status="running",
                    message=f"Rerunning node '{node_id}' (attempt {attempt}).",
                )
                try:
                    result = self._run_node(node, context)
                    context = result

                    # Build a lightweight NodeExecution-like record
                    node_exec = _make_node_exec(
                        execution_id=decision.execution_id,
                        node_id=node_id,
                        result=result,
                    )

                    # ── Validation gate ──────────────────────────────────────
                    self._emit(
                        execution_id=decision.execution_id,
                        node_id=node_id,
                        event_type="recovery_validation_started",
                        status="running",
                        message=f"Validating rerun output of '{node_id}'.",
                    )

                    validation = self.validator.validate_node_execution(node_exec)

                    if not validation.passed:
                        self._emit(
                            execution_id=decision.execution_id,
                            node_id=node_id,
                            event_type="recovery_validation_failed",
                            status="failed",
                            message=validation.message,
                        )
                        return self._failed_result(
                            decision=decision,
                            status=RecoveryStatus.FAILED,
                            message=(
                                f"Node '{node_id}' rerun produced invalid output. "
                                f"Validation: {validation.message}"
                            ),
                            evidence=tuple(validation.failures),
                        )

                    self._emit(
                        execution_id=decision.execution_id,
                        node_id=node_id,
                        event_type="recovery_validation_passed",
                        status="success",
                        message=f"Node '{node_id}' rerun validated successfully.",
                    )
                    last_exc = None
                    break  # success for this node

                except Exception as exc:
                    last_exc = exc
                    self._emit(
                        execution_id=decision.execution_id,
                        node_id=node_id,
                        event_type="recovery_failed",
                        status="failed",
                        message=f"Node '{node_id}' rerun failed: {exc}",
                    )

            if last_exc is not None:
                # Node failed after max_attempts — do not continue
                return self._failed_result(
                    decision=decision,
                    status=RecoveryStatus.FAILED,
                    message=(
                        f"Node '{node_id}' failed after {self.max_attempts} "
                        f"attempt(s): {type(last_exc).__name__}: {last_exc}"
                    ),
                    evidence=(f"rerun_failed: {node_id}: {last_exc}",),
                )

        if not found_target:
            return self._failed_result(
                decision=decision,
                status=RecoveryStatus.FAILED,
                message=(
                    f"Target node '{target_node_id}' was not found "
                    f"in the supplied nodes list."
                ),
            )

        # All nodes from target onward succeeded
        self._emit(
            execution_id=decision.execution_id,
            node_id=target_node_id or "unknown",
            event_type="recovery_completed",
            status="success",
            message="Rerun from node completed successfully.",
        )

        return RecoveryResult(
            execution_id=decision.execution_id,
            action=decision.action,
            status=RecoveryStatus.SUCCESS,
            success=True,
            recovered_from_checkpoint=checkpoint_id,
            resumed_from_node=rerun_node_id,
            message=(
                f"Rerun from node '{rerun_node_id}' completed successfully."
            ),
            evidence=(
                f"rerun_from_node: {rerun_node_id}",
                f"upstream_checkpoint: {checkpoint_id}",
            ),
            rollback_performed=checkpoint_id is not None,
            validation_passed=True,
            events=tuple(self._events),
        )

    # -----------------------------------------------------------------------
    # ROLLBACK
    # -----------------------------------------------------------------------

    def _execute_rollback(
        self,
        decision: RecoveryDecision,
    ) -> RecoveryResult:
        """
        Restore the last-known-good checkpoint without rerunning nodes.

        Steps:
          1. Look up the checkpoint.
          2. Validate checkpoint integrity.
          3. Restore the artifact.
          4. Validate the restored artifact.
          5. Return success or failure result.
        """

        checkpoint_id = decision.checkpoint_id

        if checkpoint_id is None:
            return self._failed_result(
                decision=decision,
                status=RecoveryStatus.FAILED,
                message=(
                    "ROLLBACK action requires a checkpoint_id but none "
                    "was set on the RecoveryDecision."
                ),
            )

        self._emit(
            execution_id=decision.execution_id,
            node_id=decision.target_node or "pipeline",
            event_type="recovery_checkpoint_restored",
            status="running",
            message=f"Attempting rollback to checkpoint '{checkpoint_id}'.",
            metadata={"checkpoint_id": checkpoint_id},
        )

        # ── Validate checkpoint ───────────────────────────────────────────────
        checkpoint = self._load_and_validate_checkpoint(
            checkpoint_id=checkpoint_id,
            execution_id=decision.execution_id,
        )

        # ── Restore artifact ──────────────────────────────────────────────────
        try:
            artifact = self.checkpoint_manager.restore(checkpoint_id)
        except Exception as exc:
            raise CheckpointNotFoundError(
                f"Failed to restore artifact from checkpoint "
                f"'{checkpoint_id}': {exc}"
            )

        # ── Validate restored state ───────────────────────────────────────────
        self._emit(
            execution_id=decision.execution_id,
            node_id=checkpoint.node_id,
            event_type="recovery_validation_started",
            status="running",
            message=f"Validating restored checkpoint '{checkpoint_id}'.",
        )

        ckpt_validation = self.validator.validate_checkpoint(checkpoint)

        if not ckpt_validation.passed:
            self._emit(
                execution_id=decision.execution_id,
                node_id=checkpoint.node_id,
                event_type="recovery_validation_failed",
                status="failed",
                message=ckpt_validation.message,
            )
            return self._failed_result(
                decision=decision,
                status=RecoveryStatus.FAILED,
                message=(
                    f"Checkpoint '{checkpoint_id}' failed validation after "
                    f"restore: {ckpt_validation.message}"
                ),
                evidence=tuple(ckpt_validation.failures),
            )

        self._emit(
            execution_id=decision.execution_id,
            node_id=checkpoint.node_id,
            event_type="recovery_validation_passed",
            status="success",
            message=f"Checkpoint '{checkpoint_id}' validated successfully.",
        )

        self._emit(
            execution_id=decision.execution_id,
            node_id=checkpoint.node_id,
            event_type="recovery_rollback",
            status="success",
            message=(
                f"Rollback to checkpoint '{checkpoint_id}' "
                f"(node '{checkpoint.node_id}') completed."
            ),
            metadata={"checkpoint_id": checkpoint_id},
        )

        self._emit(
            execution_id=decision.execution_id,
            node_id=checkpoint.node_id,
            event_type="recovery_completed",
            status="success",
            message="Rollback recovery completed.",
        )

        return RecoveryResult(
            execution_id=decision.execution_id,
            action=decision.action,
            status=RecoveryStatus.SUCCESS,
            success=True,
            recovered_from_checkpoint=checkpoint_id,
            resumed_from_node=None,  # rollback doesn't resume execution
            message=(
                f"Rollback to checkpoint '{checkpoint_id}' "
                f"(node '{checkpoint.node_id}') completed and validated."
            ),
            evidence=(
                f"rollback_to_checkpoint: {checkpoint_id}",
                f"checkpoint_node: {checkpoint.node_id}",
                f"validation_status: {checkpoint.validation_status}",
            ),
            rollback_performed=True,
            validation_passed=True,
            events=tuple(self._events),
        )

    # -----------------------------------------------------------------------
    # ABORT
    # -----------------------------------------------------------------------

    def _execute_abort(
        self,
        decision: RecoveryDecision,
    ) -> RecoveryResult:
        self._emit(
            execution_id=decision.execution_id,
            node_id=decision.target_node or "pipeline",
            event_type="recovery_aborted",
            status="aborted",
            message=f"Recovery aborted. Reason: {decision.reason}",
        )
        return RecoveryResult(
            execution_id=decision.execution_id,
            action=decision.action,
            status=RecoveryStatus.ABORTED,
            success=False,
            recovered_from_checkpoint=None,
            resumed_from_node=None,
            message=f"Recovery aborted: {decision.reason}",
            evidence=("abort: no safe automated recovery path",),
            rollback_performed=False,
            validation_passed=False,
            events=tuple(self._events),
        )

    # -----------------------------------------------------------------------
    # MANUAL_REVIEW
    # -----------------------------------------------------------------------

    def _execute_manual_review(
        self,
        decision: RecoveryDecision,
    ) -> RecoveryResult:
        self._emit(
            execution_id=decision.execution_id,
            node_id=decision.target_node or "pipeline",
            event_type="recovery_manual_review",
            status="pending",
            message=(
                "Manual review required. No automated action taken. "
                f"Reason: {decision.reason}"
            ),
        )
        return RecoveryResult(
            execution_id=decision.execution_id,
            action=decision.action,
            status=RecoveryStatus.PENDING_REVIEW,
            success=False,
            recovered_from_checkpoint=None,
            resumed_from_node=None,
            message=(
                "Recovery requires manual human review. "
                "No automated action was taken. "
                f"Reason: {decision.reason}"
            ),
            evidence=(
                "manual_review_required",
                f"reason: {decision.reason}",
            ),
            rollback_performed=False,
            validation_passed=False,
            events=tuple(self._events),
        )

    # -----------------------------------------------------------------------
    # QUARANTINE
    # -----------------------------------------------------------------------

    def _execute_quarantine(
        self,
        decision: RecoveryDecision,
    ) -> RecoveryResult:
        quarantine_record = self.quarantine.quarantine(
            execution_id=decision.execution_id,
            node_id=decision.target_node,
            checkpoint_id=decision.checkpoint_id,
            reason=decision.reason,
        )

        self._emit(
            execution_id=decision.execution_id,
            node_id=decision.target_node or "pipeline",
            event_type="recovery_quarantined",
            status="quarantined",
            message=(
                f"Component '{decision.target_node}' quarantined. "
                f"Reason: {decision.reason}"
            ),
            metadata=quarantine_record,
        )

        return RecoveryResult(
            execution_id=decision.execution_id,
            action=decision.action,
            status=RecoveryStatus.QUARANTINED,
            success=False,
            recovered_from_checkpoint=None,
            resumed_from_node=None,
            message=(
                f"Component '{decision.target_node}' has been quarantined "
                f"pending investigation. "
                f"Reason: {decision.reason}"
            ),
            evidence=(
                "quarantine_recorded",
                f"node: {decision.target_node}",
                f"reason: {decision.reason}",
            ),
            rollback_performed=False,
            validation_passed=False,
            events=tuple(self._events),
        )

    # -----------------------------------------------------------------------
    # Checkpoint helpers
    # -----------------------------------------------------------------------

    def _load_and_validate_checkpoint(
        self,
        checkpoint_id: str,
        execution_id: str,
    ) -> "Checkpoint":
        """
        Load a checkpoint from the manager and validate its integrity.

        Raises CheckpointNotFoundError if it doesn't exist.
        Raises CheckpointValidationError if it fails validation.
        """

        checkpoint = self.checkpoint_manager.get(checkpoint_id)

        if checkpoint is None:
            raise CheckpointNotFoundError(
                f"Checkpoint '{checkpoint_id}' not found in CheckpointManager.",
                context={"execution_id": execution_id, "checkpoint_id": checkpoint_id},
            )

        validation = self.validator.validate_checkpoint(checkpoint)

        if not validation.passed:
            raise CheckpointValidationError(
                f"Checkpoint '{checkpoint_id}' failed integrity validation: "
                f"{validation.message}",
                context={
                    "checkpoint_id": checkpoint_id,
                    "failures": list(validation.failures),
                },
            )

        return checkpoint

    # -----------------------------------------------------------------------
    # Node execution helper
    # -----------------------------------------------------------------------

    @staticmethod
    def _run_node(node: Any, context: Any) -> Any:
        """Run a single node — mirrors PipelineExecutor._run_node logic."""
        run = getattr(node, "run", None)
        if callable(run):
            return run(context)
        if callable(node):
            return node(context)
        raise TypeError(
            f"Recovery node '{node}' must provide run(context) or be callable."
        )

    @staticmethod
    def _node_id(node: Any) -> str:
        """Extract node_id — mirrors PipelineExecutor._node_id logic."""
        node_id = getattr(node, "node_id", None)
        if node_id:
            return str(node_id)
        name = getattr(node, "__name__", None)
        if name:
            return str(name)
        return node.__class__.__name__

    # -----------------------------------------------------------------------
    # Observability
    # -----------------------------------------------------------------------

    def _emit(
        self,
        *,
        execution_id: str,
        node_id: str,
        event_type: str,
        status: str,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event = NodeEvent(
            execution_id=execution_id,
            pipeline_id=self.pipeline_id,
            node_id=node_id,
            event_type=event_type,
            status=status,
            message=message,
            metadata=metadata or {},
        )
        self._events.append(event)

    # -----------------------------------------------------------------------
    # Result builders
    # -----------------------------------------------------------------------

    def _failed_result(
        self,
        decision: RecoveryDecision,
        *,
        status: str = RecoveryStatus.FAILED,
        message: str = "Recovery failed.",
        evidence: tuple[str, ...] = (),
    ) -> RecoveryResult:
        self._emit(
            execution_id=decision.execution_id,
            node_id=decision.target_node or "pipeline",
            event_type="recovery_failed",
            status="failed",
            message=message,
        )
        return RecoveryResult(
            execution_id=decision.execution_id,
            action=decision.action,
            status=status,
            success=False,
            recovered_from_checkpoint=None,
            resumed_from_node=None,
            message=message,
            evidence=evidence or ("recovery_failed",),
            rollback_performed=False,
            validation_passed=False,
            events=tuple(self._events),
        )


# ---------------------------------------------------------------------------
# Lightweight NodeExecution substitute for rerun validation
# ---------------------------------------------------------------------------


def _make_node_exec(
    *,
    execution_id: str,
    node_id: str,
    result: Any,
) -> Any:
    """
    Create a minimal NodeExecution-like object for validation purposes.

    We do NOT import NodeExecution here to avoid coupling the RecoveryExecutor
    to the full pipeline execution machinery. The validator only needs
    status, output_metadata, error_type, error_message, and node_id.
    """
    from core.pipeline.executor import NodeExecution
    from core.pipeline.status import NodeStatus
    from datetime import datetime, timezone

    output_metadata: dict[str, Any] = {
        "result_type": type(result).__name__,
    }

    shape = getattr(result, "shape", None)
    if shape is not None:
        try:
            output_metadata["shape"] = tuple(shape)
        except TypeError:
            pass

    columns = getattr(result, "columns", None)
    if columns is not None:
        try:
            output_metadata["columns"] = [str(c) for c in columns]
        except TypeError:
            pass

    now = datetime.now(timezone.utc)
    return NodeExecution(
        execution_id=execution_id,
        node_id=node_id,
        status=NodeStatus.SUCCESS,
        started_at=now,
        finished_at=now,
        output_metadata=output_metadata,
    )
