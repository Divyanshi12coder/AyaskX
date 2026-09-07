"""
core/repair/sandbox.py
-----------------------
Sandbox abstraction for future controlled repair execution.

Phase I: SANDBOX FOUNDATION
Phase J: SANDBOX BACKEND ABSTRACTION

This module defines the interface through which deterministic repair
operations will later be executed safely in an isolated environment.

CURRENT STATUS:
  - SandboxBackend interface established.
  - InProcessBackend: executes registered handlers in-process.
    IMPORTANT: This backend provides NO OS-level isolation.
    It is suitable for safe, read-only, or stateless operations only.
    Claims of "sandboxed execution" using this backend are FALSE — it is
    explicitly labelled "in_process" in SandboxResult.execution_mode.
  - Future backends: SubprocessBackend (process isolation, Windows-safe timeout).

Backend API:
  All backends implement:
    execute_step(step, handler, context) -> dict

This makes it straightforward to replace InProcessBackend with a
subprocess-based or container-based backend without changing callers.

The SandboxExecutor always reports which backend was used via
SandboxResult.execution_mode — no false claims of isolation.

Existing behavior is 100% preserved (InProcessBackend is the default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from core.repair.planner import RepairPlan, RepairStep
    from core.recovery.validator import RecoveryValidator


class SandboxStatus:
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------


class SandboxBackend:
    """
    Abstract interface for sandbox step execution.

    Implement this to support different execution environments:
      - InProcessBackend  : current default, no OS-level isolation
      - SubprocessBackend : future, process-isolated with timeout

    execute_step(step, handler, context) -> dict
      Returns a dict with at least {"success": bool, "message": str}.
    """

    @property
    def execution_mode(self) -> str:
        """Human-readable label describing the execution environment."""
        raise NotImplementedError

    def execute_step(
        self,
        step: Any,
        handler: Callable,
        context: Any,
    ) -> dict:
        raise NotImplementedError


class InProcessBackend(SandboxBackend):
    """
    Executes repair step handlers in-process (the current default).

    IMPORTANT: This backend provides NO OS-level process isolation.
    It is appropriate for:
      - Safe, read-only, or metadata-only repair operations.
      - Testing and development.

    It is NOT appropriate for:
      - Untrusted code execution.
      - Filesystem-destructive operations.
      - Security-sensitive operations.

    The execution_mode field on SandboxResult will always read
    'in_process' when using this backend, making the lack of isolation
    explicit and auditable.
    """

    @property
    def execution_mode(self) -> str:
        return "in_process"

    def execute_step(
        self,
        step: Any,
        handler: Callable,
        context: Any,
    ) -> dict:
        """Execute handler in the current process. No isolation."""
        return handler(step, context)


@dataclass(frozen=True)
class StepExecutionRecord:
    """Immutable record of a single step executed in the sandbox."""

    step_index: int
    action_type: str
    target_node: str | None
    status: str
    message: str
    validation_passed: bool
    executed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action_type": self.action_type,
            "target_node": self.target_node,
            "status": self.status,
            "message": self.message,
            "validation_passed": self.validation_passed,
            "executed_at": self.executed_at.isoformat(),
        }


@dataclass(frozen=True)
class SandboxResult:
    """
    Immutable result of a sandbox repair execution.

    Fields
    ------
    execution_id        : original pipeline execution_id
    plan_category       : hypothesis category from RepairPlan
    status              : SandboxStatus constant
    success             : True only if all steps passed validation
    steps_executed      : tuple of StepExecutionRecord
    steps_succeeded     : count of successfully validated steps
    steps_failed        : count of failed steps
    message             : human-readable outcome summary
    completed_at        : UTC timestamp
    """

    execution_id: str
    plan_category: str
    status: str
    success: bool
    steps_executed: tuple[StepExecutionRecord, ...]
    steps_succeeded: int
    steps_failed: int
    message: str
    execution_mode: str = "in_process"   # reflects SandboxBackend used
    completed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "plan_category": self.plan_category,
            "status": self.status,
            "success": self.success,
            "steps_succeeded": self.steps_succeeded,
            "steps_failed": self.steps_failed,
            "message": self.message,
            "execution_mode": self.execution_mode,
            "steps_executed": [s.to_dict() for s in self.steps_executed],
            "completed_at": self.completed_at.isoformat(),
        }


class SandboxExecutor:
    """
    Interface for controlled repair step execution.

    Phase I: Steps that require no external I/O are simulated via
    registered handlers. No production files are modified.

    To register a handler for a repair action type:
        executor.register_handler("RERUN_NODE", my_callable)

    Handlers receive (step, context) and return a dict with at least
    {"success": bool, "message": str}.

    If no handler is registered for a step's action_type,
    the step is SKIPPED (not failed), as the operation is deferred
    to a future sandbox implementation.
    """

    def __init__(
        self,
        backend: SandboxBackend | None = None,
    ) -> None:
        """
        Parameters
        ----------
        backend : SandboxBackend, optional
            Execution backend.  Defaults to InProcessBackend (no OS isolation).
            Pass a different backend to change execution environment.
            The backend's execution_mode is recorded in every SandboxResult.
        """
        self._backend = backend if backend is not None else InProcessBackend()
        self._handlers: dict[str, Callable] = {}

    def register_handler(
        self,
        action_type: str,
        handler: Callable,
    ) -> None:
        """Register a callable handler for a specific action type."""
        self._handlers[action_type] = handler

    def execute_plan(
        self,
        plan: "RepairPlan",
        *,
        context: Any = None,
    ) -> SandboxResult:
        """
        Execute a RepairPlan step by step.

        Steps without a registered handler are SKIPPED.
        Steps that fail halt execution immediately (no infinite retry).
        All outcomes are recorded in SandboxResult.
        """

        step_records: list[StepExecutionRecord] = []
        succeeded = 0
        failed = 0
        mode = self._backend.execution_mode

        for step in plan.steps:
            record = self._execute_step(step, context)
            step_records.append(record)

            if record.status == SandboxStatus.FAILED:
                failed += 1
                # Halt on first failure
                final_status = SandboxStatus.PARTIAL if succeeded > 0 else SandboxStatus.FAILED
                return SandboxResult(
                    execution_id=plan.execution_id,
                    plan_category=plan.hypothesis_category,
                    status=final_status,
                    success=False,
                    steps_executed=tuple(step_records),
                    steps_succeeded=succeeded,
                    steps_failed=failed,
                    message=(
                        f"Sandbox halted at step {step.step_index} "
                        f"({step.action_type}): {record.message}"
                    ),
                    execution_mode=mode,
                    completed_at=datetime.now(timezone.utc),
                )
            elif record.status == SandboxStatus.SUCCESS:
                succeeded += 1

        # All steps completed
        overall_success = failed == 0
        return SandboxResult(
            execution_id=plan.execution_id,
            plan_category=plan.hypothesis_category,
            status=SandboxStatus.SUCCESS if overall_success else SandboxStatus.PARTIAL,
            success=overall_success,
            steps_executed=tuple(step_records),
            steps_succeeded=succeeded,
            steps_failed=failed,
            message=(
                f"Sandbox completed: {succeeded} step(s) succeeded, "
                f"{failed} failed."
            ),
            execution_mode=mode,
            completed_at=datetime.now(timezone.utc),
        )

    def _execute_step(
        self,
        step: "RepairStep",
        context: Any,
    ) -> StepExecutionRecord:
        handler = self._handlers.get(step.action_type)

        if handler is None:
            # No handler registered — defer to future implementation
            return StepExecutionRecord(
                step_index=step.step_index,
                action_type=step.action_type,
                target_node=step.target_node,
                status=SandboxStatus.SKIPPED,
                message=(
                    f"No handler registered for '{step.action_type}'. "
                    f"Step deferred to future sandbox implementation."
                ),
                validation_passed=False,
                executed_at=datetime.now(timezone.utc),
            )

        try:
            result = self._backend.execute_step(step, handler, context)
            success = bool(result.get("success", False))
            message = str(result.get("message", ""))
            validation_ok = bool(result.get("validation_passed", success))

            if step.requires_validation and not validation_ok:
                return StepExecutionRecord(
                    step_index=step.step_index,
                    action_type=step.action_type,
                    target_node=step.target_node,
                    status=SandboxStatus.FAILED,
                    message=(
                        f"Validation gate failed after step '{step.action_type}': "
                        f"{message}"
                    ),
                    validation_passed=False,
                    executed_at=datetime.now(timezone.utc),
                )

            return StepExecutionRecord(
                step_index=step.step_index,
                action_type=step.action_type,
                target_node=step.target_node,
                status=SandboxStatus.SUCCESS if success else SandboxStatus.FAILED,
                message=message,
                validation_passed=validation_ok,
                executed_at=datetime.now(timezone.utc),
            )

        except Exception as exc:
            return StepExecutionRecord(
                step_index=step.step_index,
                action_type=step.action_type,
                target_node=step.target_node,
                status=SandboxStatus.FAILED,
                message=f"Handler raised: {type(exc).__name__}: {exc}",
                validation_passed=False,
                executed_at=datetime.now(timezone.utc),
            )
