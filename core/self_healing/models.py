"""
core/self_healing/models.py
-----------------------------
Immutable result models for the SelfHealingOrchestrator.

Phase M: END-TO-END SELF-HEALING ORCHESTRATOR

All objects are frozen dataclasses.
They carry the complete, inspectable audit trail of one self-healing attempt:

  DETECT → LOCALIZE → DIAGNOSE → PLAN → SAFETY_CHECK
  → SANDBOX → VALIDATE → RESUME / ROLLBACK
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SelfHealingStatus(str, Enum):
    """
    Lifecycle states of a self-healing attempt.

    Terminal states: RESUMED, ROLLED_BACK, QUARANTINED, MANUAL_REVIEW,
                     ABORTED, FAILED, NO_FAULT
    """

    # Analysis phases
    DETECTED = "detected"
    LOCALIZED = "localized"
    DIAGNOSED = "diagnosed"
    PLANNED = "planned"
    SAFETY_CHECKED = "safety_checked"

    # Execution phases
    SANDBOX_EXECUTING = "sandbox_executing"
    VALIDATING = "validating"

    # Terminal states
    RESUMED = "resumed"           # repair succeeded; pipeline can continue
    ROLLED_BACK = "rolled_back"   # repair failed; rolled back to checkpoint
    QUARANTINED = "quarantined"   # artifact quarantined pending review
    MANUAL_REVIEW = "manual_review"  # human review required; no automated action
    ABORTED = "aborted"           # no safe path; execution stopped
    FAILED = "failed"             # unexpected error during orchestration
    NO_FAULT = "no_fault"         # pipeline succeeded; no healing needed


@dataclass(frozen=True)
class SelfHealingTimestamps:
    """UTC timestamps recorded at each lifecycle transition."""

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    detected_at: datetime | None = None
    localized_at: datetime | None = None
    diagnosed_at: datetime | None = None
    planned_at: datetime | None = None
    sandbox_started_at: datetime | None = None
    sandbox_completed_at: datetime | None = None
    validated_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, str | None]:
        def _iso(v: datetime | None) -> str | None:
            return v.isoformat() if v is not None else None

        return {
            "started_at": _iso(self.started_at),
            "detected_at": _iso(self.detected_at),
            "localized_at": _iso(self.localized_at),
            "diagnosed_at": _iso(self.diagnosed_at),
            "planned_at": _iso(self.planned_at),
            "sandbox_started_at": _iso(self.sandbox_started_at),
            "sandbox_completed_at": _iso(self.sandbox_completed_at),
            "validated_at": _iso(self.validated_at),
            "completed_at": _iso(self.completed_at),
        }


@dataclass(frozen=True)
class SelfHealingResult:
    """
    Immutable, complete result of one self-healing attempt.

    Every field in the decision chain is included so the entire
    reasoning process is inspectable and auditable.

    Fields
    ------
    execution_id          : original pipeline execution_id
    success               : True iff repair validated and pipeline resumed
    final_status          : SelfHealingStatus at completion
    fault_report          : serialized FaultReport dict (or None)
    localization          : serialized FaultLocalization dict (or None)
    root_cause            : serialized RootCauseReport dict (or None)
    recovery_decision     : serialized RecoveryDecision dict (or None)
    repair_plan           : serialized RepairPlan dict (or None)
    sandbox_result        : serialized SandboxResult dict (or None)
    recovery_result       : serialized RecoveryResult dict (or None)
    validation_result     : serialized ValidationResult dict (or None)
    resumed_from_node     : node_id where execution will resume (or None)
    rolled_back_to_checkpoint : checkpoint_id of rollback point (or None)
    audit_references      : tuple of audit event IDs / log references
    errors                : tuple of error strings encountered
    timestamps            : SelfHealingTimestamps
    observability_events  : tuple of NodeEvent records produced during healing
    """

    execution_id: str
    success: bool
    final_status: SelfHealingStatus

    fault_report: dict[str, Any] | None = None
    localization: dict[str, Any] | None = None
    root_cause: dict[str, Any] | None = None
    recovery_decision: dict[str, Any] | None = None
    repair_plan: dict[str, Any] | None = None
    sandbox_result: dict[str, Any] | None = None
    recovery_result: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None

    resumed_from_node: str | None = None
    rolled_back_to_checkpoint: str | None = None

    audit_references: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    timestamps: SelfHealingTimestamps = field(
        default_factory=SelfHealingTimestamps
    )

    observability_events: tuple[Any, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Return a fully JSON-serializable dictionary."""
        return {
            "execution_id": self.execution_id,
            "success": self.success,
            "final_status": self.final_status.value,
            "fault_report": self.fault_report,
            "localization": self.localization,
            "root_cause": self.root_cause,
            "recovery_decision": self.recovery_decision,
            "repair_plan": self.repair_plan,
            "sandbox_result": self.sandbox_result,
            "recovery_result": self.recovery_result,
            "validation_result": self.validation_result,
            "resumed_from_node": self.resumed_from_node,
            "rolled_back_to_checkpoint": self.rolled_back_to_checkpoint,
            "audit_references": list(self.audit_references),
            "errors": list(self.errors),
            "timestamps": self.timestamps.to_dict(),
        }
