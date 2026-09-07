"""
core/security/recovery.py
--------------------------
SecurityRecoveryManager — conservative, auditable artifact security response.

Responsibilities:
  - Identify integrity failures and classify severity.
  - Quarantine affected artifacts (metadata record only — no file deletion).
  - Record every action as a SecurityAuditEvent.
  - Select trusted checkpoint candidates via ArtifactIntegrityChecker.
  - Produce structured SecurityRecoveryDecision for human/executor review.

This manager does NOT:
  - Delete production files.
  - Revoke credentials.
  - Rotate credentials automatically.
  - Deploy arbitrary code.
  - Overwrite trusted artifacts.
  - Bypass validation gates.

All destructive operations require explicit human authorization.
Every decision is recorded in the audit log before any action is taken.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.integrity.checker import ArtifactIntegrityChecker
from core.integrity.models import IntegrityStatus
from core.security.audit import SecurityAuditLogger
from core.security.models import (
    QuarantineRecord,
    SecurityAuditEvent,
    SecurityEventType,
    SecurityRecoveryDecision,
    SecuritySeverity,
)

if TYPE_CHECKING:
    from core.integrity.models import CheckpointTrustReport, IntegrityResult
    from core.pipeline.checkpoints.manager import Checkpoint, CheckpointManager


_COMPONENT = "SecurityRecoveryManager"


class SecurityRecoveryManager:
    """
    Conservative, auditable security response for artifact integrity failures.

    All decisions are structured (SecurityRecoveryDecision).
    All actions are logged (SecurityAuditEvent).
    No destructive filesystem operations.

    Usage
    -----
    manager = SecurityRecoveryManager(audit_logger)

    # When an integrity check fails:
    decision = manager.handle_integrity_failure(
        integrity_result=result,
        execution_id="exec-001",
        artifact_id="my_model:exec-001",
        checkpoint_manager=ckpt_manager,
    )
    """

    def __init__(
        self,
        audit_logger: SecurityAuditLogger | None = None,
    ) -> None:
        self.audit_logger = audit_logger or SecurityAuditLogger()
        self._checker = ArtifactIntegrityChecker()
        self._quarantine_records: list[QuarantineRecord] = []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def handle_integrity_failure(
        self,
        integrity_result: "IntegrityResult",
        *,
        execution_id: str,
        artifact_id: str,
        checkpoint_manager: "CheckpointManager | None" = None,
    ) -> SecurityRecoveryDecision:
        """
        Respond to an integrity check failure.

        Steps:
        1. Record a INTEGRITY_CHECK_FAILED audit event.
        2. Quarantine the artifact (metadata record only).
        3. Find a trusted checkpoint candidate (if checkpoint_manager given).
        4. Produce a SecurityRecoveryDecision.
        5. Record a SECURITY_AUDIT_RECORDED event.

        Returns
        -------
        SecurityRecoveryDecision — always. Never raises to the caller.
        """

        # 1. Log the integrity failure
        severity = self._map_severity(integrity_result.status)
        fail_event = SecurityAuditEvent(
            event_type=SecurityEventType.INTEGRITY_CHECK_FAILED,
            execution_id=execution_id,
            component=_COMPONENT,
            severity=severity,
            action=f"Integrity check failed for artifact '{artifact_id}'",
            reason=integrity_result.reason,
            metadata={
                "artifact_id": artifact_id,
                "artifact_path": integrity_result.artifact_path,
                "status": integrity_result.status.value,
                "expected_checksum": integrity_result.expected_checksum,
                "actual_checksum": integrity_result.actual_checksum,
            },
        )
        self.audit_logger.record(fail_event)

        # 2. Quarantine (metadata only — no file operations)
        quarantine_record = self._quarantine_artifact(
            artifact_id=artifact_id,
            artifact_path=integrity_result.artifact_path,
            reason=integrity_result.reason,
            execution_id=execution_id,
            integrity_status=integrity_result.status.value,
            audit_event_id=fail_event.event_id,
        )

        # 3. Find trusted checkpoint
        trusted_checkpoint_id = None
        if checkpoint_manager is not None:
            trusted_checkpoint_id = self._find_trusted_checkpoint(
                checkpoint_manager, execution_id
            )

        # 4. Decide
        decision = self._make_decision(
            integrity_result=integrity_result,
            execution_id=execution_id,
            artifact_id=artifact_id,
            trusted_checkpoint_id=trusted_checkpoint_id,
            fail_event_id=fail_event.event_id,
        )

        # 5. Log the decision
        self.audit_logger.record(SecurityAuditEvent(
            event_type=SecurityEventType.SECURITY_AUDIT_RECORDED,
            execution_id=execution_id,
            component=_COMPONENT,
            severity=SecuritySeverity.INFO,
            action=f"Security decision recorded: {decision.recommended_action}",
            reason=decision.rationale,
            metadata={
                "artifact_id": artifact_id,
                "recommended_action": decision.recommended_action,
                "trusted_checkpoint_id": trusted_checkpoint_id,
                "requires_human_review": decision.requires_human_review,
                "quarantine_audit_event_id": quarantine_record.audit_event_id,
            },
        ))

        return decision

    # ------------------------------------------------------------------
    # Trusted checkpoint selection
    # ------------------------------------------------------------------

    def select_trusted_checkpoint(
        self,
        checkpoints: list["Checkpoint"],
        execution_id: str,
    ) -> "Checkpoint | None":
        """
        Select the most recent checkpoint that is both structurally valid
        and integrity verified.

        A corrupted newer checkpoint does NOT override a trusted older one.
        Emits observability events for accepted/rejected checkpoints.
        """
        trusted = self._checker.select_trusted_checkpoint(checkpoints)

        if trusted is not None:
            self.audit_logger.record(SecurityAuditEvent(
                event_type=SecurityEventType.TRUSTED_CHECKPOINT_SELECTED,
                execution_id=execution_id,
                component=_COMPONENT,
                severity=SecuritySeverity.INFO,
                action=f"Trusted checkpoint selected: {trusted.checkpoint_id}",
                reason="Checkpoint is structurally valid and integrity verified.",
                metadata={"checkpoint_id": trusted.checkpoint_id},
            ))
        else:
            self.audit_logger.record(SecurityAuditEvent(
                event_type=SecurityEventType.UNTRUSTED_CHECKPOINT_REJECTED,
                execution_id=execution_id,
                component=_COMPONENT,
                severity=SecuritySeverity.WARNING,
                action="No trusted checkpoint found among candidates.",
                reason="All candidates failed integrity or structural checks.",
                metadata={"candidate_count": len(checkpoints)},
            ))

        return trusted

    # ------------------------------------------------------------------
    # Quarantine records (read-only access)
    # ------------------------------------------------------------------

    @property
    def quarantine_records(self) -> tuple[QuarantineRecord, ...]:
        """All quarantine records (metadata only, never destructive)."""
        return tuple(self._quarantine_records)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _quarantine_artifact(
        self,
        artifact_id: str,
        artifact_path: str,
        reason: str,
        execution_id: str,
        integrity_status: str,
        audit_event_id: str,
    ) -> QuarantineRecord:
        """
        Record a quarantine action (metadata only — NO file deletion or move).

        Emits ARTIFACT_QUARANTINED audit event.
        """
        record = QuarantineRecord(
            artifact_id=artifact_id,
            artifact_path=artifact_path,
            quarantine_reason=reason,
            quarantined_at=datetime.now(timezone.utc),
            execution_id=execution_id,
            integrity_status=integrity_status,
            audit_event_id=audit_event_id,
        )
        self._quarantine_records.append(record)

        self.audit_logger.record(SecurityAuditEvent(
            event_type=SecurityEventType.ARTIFACT_QUARANTINED,
            execution_id=execution_id,
            component=_COMPONENT,
            severity=SecuritySeverity.HIGH,
            action=f"Artifact '{artifact_id}' recorded as quarantined (metadata only).",
            reason=(
                "No automatic file deletion or credential revocation. "
                "Human review required for destructive action."
            ),
            metadata={
                "artifact_id": artifact_id,
                "artifact_path": artifact_path,
                "integrity_status": integrity_status,
                "quarantine_audit_event_id": audit_event_id,
            },
        ))

        return record

    def _find_trusted_checkpoint(
        self,
        checkpoint_manager: "CheckpointManager",
        execution_id: str,
    ) -> str | None:
        """Find the most recent trusted checkpoint for the given execution."""
        all_checkpoints = list(checkpoint_manager.list())
        exec_checkpoints = [
            c for c in all_checkpoints
            if c.execution_id == execution_id
        ]
        # Prefer execution-scoped, fall back to any trusted
        candidates = exec_checkpoints if exec_checkpoints else all_checkpoints
        trusted = self._checker.select_trusted_checkpoint(candidates)
        return getattr(trusted, "checkpoint_id", None) if trusted else None

    def _make_decision(
        self,
        integrity_result: "IntegrityResult",
        execution_id: str,
        artifact_id: str,
        trusted_checkpoint_id: str | None,
        fail_event_id: str,
    ) -> SecurityRecoveryDecision:
        """
        Produce a conservative, deterministic SecurityRecoveryDecision.

        Policy:
          FAILED (checksum mismatch) + trusted checkpoint →
              "quarantine_and_rollback"
          FAILED + no trusted checkpoint →
              "quarantine_manual_review"
          NO_MANIFEST + trusted checkpoint →
              "rollback_to_trusted"
          NO_MANIFEST + no checkpoint →
              "block_and_review"
          Any other →
              "block_and_review"
        """
        status = integrity_result.status

        if status == IntegrityStatus.FAILED:
            if trusted_checkpoint_id:
                action = "quarantine_and_rollback"
                rationale = (
                    f"Artifact '{artifact_id}' has a checksum mismatch — "
                    "it may have been modified. Quarantine recorded. "
                    f"Trusted checkpoint '{trusted_checkpoint_id}' is available for rollback. "
                    "Human authorization required before rollback executes."
                )
                human_review = True
            else:
                action = "quarantine_manual_review"
                rationale = (
                    f"Artifact '{artifact_id}' has a checksum mismatch and "
                    "no trusted checkpoint is available. "
                    "Manual review and human authorization required before any recovery action."
                )
                human_review = True

        elif status == IntegrityStatus.NO_MANIFEST:
            if trusted_checkpoint_id:
                action = "rollback_to_trusted"
                rationale = (
                    f"Artifact '{artifact_id}' has no integrity manifest (legacy artifact). "
                    "It cannot be verified. "
                    f"Trusted checkpoint '{trusted_checkpoint_id}' is available as a safer alternative."
                )
                human_review = True
            else:
                action = "block_and_review"
                rationale = (
                    f"Artifact '{artifact_id}' is unverified and no trusted checkpoint exists. "
                    "Cannot proceed safely without human review."
                )
                human_review = True

        else:
            action = "block_and_review"
            rationale = (
                f"Unexpected integrity status '{status.value}' for '{artifact_id}'. "
                "Blocking recovery until human review clears the artifact."
            )
            human_review = True

        return SecurityRecoveryDecision(
            execution_id=execution_id,
            recommended_action=action,
            artifact_id=artifact_id,
            trusted_checkpoint_id=trusted_checkpoint_id,
            rationale=rationale,
            requires_human_review=human_review,
            audit_event_id=fail_event_id,
        )

    @staticmethod
    def _map_severity(status: IntegrityStatus) -> SecuritySeverity:
        if status == IntegrityStatus.FAILED:
            return SecuritySeverity.CRITICAL
        if status == IntegrityStatus.NO_MANIFEST:
            return SecuritySeverity.WARNING
        if status == IntegrityStatus.ARTIFACT_MISSING:
            return SecuritySeverity.HIGH
        return SecuritySeverity.INFO
