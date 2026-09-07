"""
core/recovery/models.py
-----------------------
Immutable result models for AyaskX checkpoint-aware recovery execution.

Phase: CHECKPOINT-AWARE RECOVERY EXECUTION

All dataclasses here are frozen. They are the auditable record of what the
RecoveryExecutor actually did, not what was decided. They are separate from
RecoveryDecision (which records intent) — this records outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.recovery.decision import RecoveryActionType


# ---------------------------------------------------------------------------
# RecoveryStatus
# ---------------------------------------------------------------------------


class RecoveryStatus:
    """String constants for recovery outcome status."""

    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"
    PENDING_REVIEW = "pending_review"
    QUARANTINED = "quarantined"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# RecoveryResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecoveryResult:
    """
    Immutable, auditable record of a completed recovery attempt.

    Produced by RecoveryExecutor after executing a RecoveryDecision.
    Never mutated after construction.

    Fields
    ------
    execution_id             : original pipeline execution_id
    action                   : the RecoveryActionType that was executed
    status                   : RecoveryStatus constant (success/failed/…)
    success                  : True only if recovery completed AND validated
    recovered_from_checkpoint: checkpoint_id used for rollback/rerun, or None
    resumed_from_node        : node_id where execution resumed, or None
    message                  : human-readable outcome summary
    evidence                 : tuple of evidence strings (auditable)
    rollback_performed       : True if a checkpoint restore was executed
    validation_passed        : True if the validation gate accepted the output
    events                   : structured NodeEvent records from this recovery
    timestamp                : UTC time the result was recorded
    """

    execution_id: str
    action: RecoveryActionType
    status: str
    success: bool

    recovered_from_checkpoint: str | None
    resumed_from_node: str | None

    message: str
    evidence: tuple[str, ...]

    rollback_performed: bool
    validation_passed: bool

    events: tuple[Any, ...] = field(default_factory=tuple)

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "execution_id": self.execution_id,
            "action": self.action.value,
            "status": self.status,
            "success": self.success,
            "recovered_from_checkpoint": self.recovered_from_checkpoint,
            "resumed_from_node": self.resumed_from_node,
            "message": self.message,
            "evidence": list(self.evidence),
            "rollback_performed": self.rollback_performed,
            "validation_passed": self.validation_passed,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# ValidationCheck / ValidationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationCheck:
    """
    A single named validation check with pass/fail outcome.
    """

    name: str
    passed: bool
    message: str = ""


@dataclass(frozen=True)
class ValidationResult:
    """
    Immutable result from the RecoveryValidator.

    Fields
    ------
    passed   : True only when ALL checks passed
    checks   : tuple of individual ValidationCheck results
    failures : tuple of check names that failed (empty on full pass)
    message  : human-readable summary
    """

    passed: bool
    checks: tuple[ValidationCheck, ...]
    failures: tuple[str, ...]
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": list(self.failures),
            "message": self.message,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                }
                for c in self.checks
            ],
        }
