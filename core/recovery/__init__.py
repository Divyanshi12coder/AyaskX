"""
core/recovery/__init__.py
-------------------------
Public API for the AyaskX recovery subsystem.

Phase: CHECKPOINT-AWARE RECOVERY EXECUTION
"""

from core.recovery.decision import (
    RecoveryActionType,
    RecoveryDecision,
    RecoveryDecisionEngine,
)
from core.recovery.models import (
    RecoveryResult,
    RecoveryStatus,
    ValidationCheck,
    ValidationResult,
)
from core.recovery.validator import RecoveryValidator
from core.recovery.executor import ArtifactQuarantine, RecoveryExecutor
from core.recovery.errors import (
    CheckpointNotFoundError,
    CheckpointValidationError,
    NodeRerunError,
    QuarantineRequired,
    RecoveryError,
    UnsafeRecoveryError,
)


__all__ = [
    # Decision (pure policy)
    "RecoveryActionType",
    "RecoveryDecision",
    "RecoveryDecisionEngine",
    # Execution
    "RecoveryExecutor",
    "ArtifactQuarantine",
    # Validation
    "RecoveryValidator",
    "ValidationCheck",
    "ValidationResult",
    # Results
    "RecoveryResult",
    "RecoveryStatus",
    # Errors
    "RecoveryError",
    "CheckpointNotFoundError",
    "CheckpointValidationError",
    "NodeRerunError",
    "QuarantineRequired",
    "UnsafeRecoveryError",
]
