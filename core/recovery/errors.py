"""
core/recovery/errors.py
-----------------------
Structured exception hierarchy for AyaskX recovery execution.

All exceptions carry structured context for auditing and logging.
They are raised by RecoveryExecutor and caught at the call boundary
to produce a failed RecoveryResult — they never escape silently.
"""

from __future__ import annotations


class RecoveryError(Exception):
    """Base class for all AyaskX recovery errors."""

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message)
        self.context: dict = context or {}


class CheckpointNotFoundError(RecoveryError):
    """
    Raised when a required checkpoint does not exist in CheckpointManager.
    Recovery cannot proceed; the executor will produce a failed result.
    """


class CheckpointValidationError(RecoveryError):
    """
    Raised when a checkpoint exists but fails integrity or schema validation.
    Recovery cannot proceed safely; the executor will produce a failed result.
    """


class NodeRerunError(RecoveryError):
    """
    Raised when a node fails during a recovery rerun attempt.
    The executor catches this and produces a failed RecoveryResult.
    Infinite retries are not permitted.
    """


class QuarantineRequired(RecoveryError):
    """
    Raised when a recovery action requires quarantine but the
    caller has not confirmed. Not used for destructive quarantine —
    that is future work.
    """


class UnsafeRecoveryError(RecoveryError):
    """
    Raised when the executor detects an unsafe recovery attempt,
    e.g., trying to execute MANUAL_REVIEW automatically.
    """
