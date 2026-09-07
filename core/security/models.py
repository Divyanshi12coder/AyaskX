"""
core/security/models.py
-----------------------
Immutable security domain models for AyaskX.

Design:
- All objects are frozen dataclasses (immutable after construction).
- JSON-serializable via to_dict().
- No I/O or side effects in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class SecurityEventType(str, Enum):
    """Classification of security-relevant events."""

    INTEGRITY_CHECK_STARTED   = "integrity_check_started"
    INTEGRITY_CHECK_PASSED    = "integrity_check_passed"
    INTEGRITY_CHECK_FAILED    = "integrity_check_failed"
    ARTIFACT_QUARANTINED      = "artifact_quarantined"
    SECURITY_REVIEW_REQUIRED  = "security_review_required"
    TRUSTED_CHECKPOINT_SELECTED  = "trusted_checkpoint_selected"
    UNTRUSTED_CHECKPOINT_REJECTED = "untrusted_checkpoint_rejected"
    RECOVERY_BLOCKED_INTEGRITY   = "recovery_blocked_by_integrity"
    SECURITY_AUDIT_RECORDED   = "security_audit_recorded"
    ARTIFACT_LOADED_UNVERIFIED = "artifact_loaded_unverified"
    ARTIFACT_LOAD_BLOCKED     = "artifact_load_blocked"


class SecuritySeverity(str, Enum):
    """Severity of a security event."""

    INFO     = "info"
    WARNING  = "warning"
    HIGH     = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SecurityAuditEvent:
    """
    Immutable, auditable record of a security-relevant action in AyaskX.

    Every meaningful integrity/recovery/quarantine action produces one
    of these. They are append-only: once recorded they are never mutated.

    Fields
    ------
    event_id       : UUID for this event
    event_type     : SecurityEventType classification
    execution_id   : originating pipeline execution
    component      : module/class that produced the event
    severity       : SecuritySeverity
    timestamp      : UTC time the event occurred
    action         : human-readable action description
    reason         : why this event was emitted
    metadata       : arbitrary JSON-serializable context
    """

    event_type: SecurityEventType
    execution_id: str
    component: str
    severity: SecuritySeverity
    action: str
    reason: str

    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "execution_id": self.execution_id,
            "component": self.component,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class QuarantineRecord:
    """
    Metadata-only record of a quarantined artifact.

    IMPORTANT: This record documents a quarantine action.
    It does NOT delete or move any file automatically.
    All destructive filesystem operations require explicit human authorization.

    Fields
    ------
    artifact_id        : stable identifier (model_name:execution_id)
    artifact_path      : original path on disk
    quarantine_reason  : why the artifact was quarantined
    quarantined_at     : UTC timestamp
    execution_id       : originating pipeline execution
    integrity_status   : IntegrityStatus value at quarantine time
    audit_event_id     : event_id of the associated SecurityAuditEvent
    """

    artifact_id: str
    artifact_path: str
    quarantine_reason: str
    quarantined_at: datetime
    execution_id: str
    integrity_status: str
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_path": self.artifact_path,
            "quarantine_reason": self.quarantine_reason,
            "quarantined_at": self.quarantined_at.isoformat(),
            "execution_id": self.execution_id,
            "integrity_status": self.integrity_status,
            "audit_event_id": self.audit_event_id,
        }


@dataclass(frozen=True)
class SecurityRecoveryDecision:
    """
    Structured decision from SecurityRecoveryManager.

    The manager decides what SHOULD happen, but does NOT execute
    destructive actions automatically.

    Possible recommended_action values:
      "quarantine_and_rollback"  — artifact compromised; roll back to trusted ckpt
      "quarantine_manual_review" — artifact compromised; no trusted checkpoint
      "rollback_to_trusted"      — artifact unverified; trusted checkpoint available
      "block_and_review"         — cannot proceed safely; human review required

    Fields
    ------
    execution_id           : originating execution
    recommended_action     : string action label (see above)
    artifact_id            : artifact under review
    trusted_checkpoint_id  : suggested rollback target, or None
    rationale              : human-readable explanation
    requires_human_review  : True when no automated resolution is safe
    audit_event_id         : associated SecurityAuditEvent.event_id
    """

    execution_id: str
    recommended_action: str
    artifact_id: str | None
    trusted_checkpoint_id: str | None
    rationale: str
    requires_human_review: bool
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "recommended_action": self.recommended_action,
            "artifact_id": self.artifact_id,
            "trusted_checkpoint_id": self.trusted_checkpoint_id,
            "rationale": self.rationale,
            "requires_human_review": self.requires_human_review,
            "audit_event_id": self.audit_event_id,
        }
