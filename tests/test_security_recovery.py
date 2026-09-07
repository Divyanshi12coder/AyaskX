"""
tests/test_security_recovery.py
--------------------------------
Tests for SecurityRecoveryManager, QuarantineRecord, and SecurityRecoveryDecision.

Verifies:
- Integrity failures trigger structured decisions (never arbitrary actions).
- Quarantine is metadata-only (no file deletion).
- No credentials are revoked.
- No production files are mutated.
- Trusted checkpoint selection is correct.
- Every action is audited.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from core.integrity.models import IntegrityResult, IntegrityStatus
from core.security.audit import SecurityAuditLogger
from core.security.models import (
    QuarantineRecord,
    SecurityAuditEvent,
    SecurityEventType,
    SecurityRecoveryDecision,
    SecuritySeverity,
)
from core.security.recovery import SecurityRecoveryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _failed_result(
    artifact_path="/model/artifact.joblib",
    status=IntegrityStatus.FAILED,
    expected="aaa",
    actual="bbb",
    reason="Checksum mismatch",
) -> IntegrityResult:
    return IntegrityResult(
        valid=False,
        status=status,
        artifact_path=artifact_path,
        algorithm="sha256",
        expected_checksum=expected,
        actual_checksum=actual,
        checked_at=datetime.now(timezone.utc),
        reason=reason,
    )


def _passed_result(artifact_path="/model/artifact.joblib") -> IntegrityResult:
    return IntegrityResult(
        valid=True,
        status=IntegrityStatus.PASSED,
        artifact_path=artifact_path,
        algorithm="sha256",
        expected_checksum="abc",
        actual_checksum="abc",
        checked_at=datetime.now(timezone.utc),
        reason="OK",
    )


def _no_manifest_result(artifact_path="/model/artifact.joblib") -> IntegrityResult:
    return IntegrityResult(
        valid=False,
        status=IntegrityStatus.NO_MANIFEST,
        artifact_path=artifact_path,
        algorithm="sha256",
        expected_checksum=None,
        actual_checksum=None,
        checked_at=datetime.now(timezone.utc),
        reason="No manifest found.",
    )


# ---------------------------------------------------------------------------
# QuarantineRecord
# ---------------------------------------------------------------------------

class TestQuarantineRecord:
    def test_is_immutable(self):
        r = QuarantineRecord(
            artifact_id="m:e1",
            artifact_path="/path",
            quarantine_reason="mismatch",
            quarantined_at=datetime.now(timezone.utc),
            execution_id="e1",
            integrity_status="failed",
            audit_event_id="evt-1",
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            r.artifact_path = "/other"  # type: ignore[misc]

    def test_to_dict_json_safe(self):
        r = QuarantineRecord(
            artifact_id="m:e1",
            artifact_path="/path",
            quarantine_reason="mismatch",
            quarantined_at=datetime.now(timezone.utc),
            execution_id="e1",
            integrity_status="failed",
            audit_event_id="evt-1",
        )
        assert json.dumps(r.to_dict())


# ---------------------------------------------------------------------------
# SecurityRecoveryDecision
# ---------------------------------------------------------------------------

class TestSecurityRecoveryDecision:
    def test_is_immutable(self):
        d = SecurityRecoveryDecision(
            execution_id="e1",
            recommended_action="quarantine_and_rollback",
            artifact_id="m:e1",
            trusted_checkpoint_id="ckpt-1",
            rationale="Checksum mismatch.",
            requires_human_review=True,
            audit_event_id="evt-1",
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            d.recommended_action = "delete_everything"  # type: ignore[misc]

    def test_to_dict_json_safe(self):
        d = SecurityRecoveryDecision(
            execution_id="e1",
            recommended_action="quarantine_and_rollback",
            artifact_id="m:e1",
            trusted_checkpoint_id="ckpt-1",
            rationale="Mismatch",
            requires_human_review=True,
            audit_event_id="evt-1",
        )
        assert json.dumps(d.to_dict())


# ---------------------------------------------------------------------------
# SecurityRecoveryManager
# ---------------------------------------------------------------------------

class TestSecurityRecoveryManager:
    def _manager(self) -> tuple[SecurityRecoveryManager, SecurityAuditLogger]:
        logger = SecurityAuditLogger()
        mgr = SecurityRecoveryManager(audit_logger=logger)
        return mgr, logger

    # ------------------------------------------------------------------
    # handle_integrity_failure — FAILED + no checkpoint
    # ------------------------------------------------------------------

    def test_failed_no_checkpoint_gives_manual_review(self):
        mgr, logger = self._manager()
        result = _failed_result()
        decision = mgr.handle_integrity_failure(
            result,
            execution_id="e1",
            artifact_id="m:e1",
        )
        assert decision.recommended_action == "quarantine_manual_review"
        assert decision.trusted_checkpoint_id is None
        assert decision.requires_human_review is True

    # ------------------------------------------------------------------
    # handle_integrity_failure — FAILED + trusted checkpoint
    # ------------------------------------------------------------------

    def test_failed_with_checkpoint_gives_quarantine_and_rollback(self):
        mgr, logger = self._manager()

        with tempfile.TemporaryDirectory() as td:
            from core.pipeline.checkpoints.manager import CheckpointManager
            ckpt_mgr = CheckpointManager(root_dir=td)
            ckpt_mgr.create(execution_id="e1", node_id="training", artifact={"x": 1})

            result = _failed_result()
            decision = mgr.handle_integrity_failure(
                result,
                execution_id="e1",
                artifact_id="m:e1",
                checkpoint_manager=ckpt_mgr,
            )
        assert decision.recommended_action == "quarantine_and_rollback"
        assert decision.trusted_checkpoint_id is not None
        assert decision.requires_human_review is True

    # ------------------------------------------------------------------
    # handle_integrity_failure — NO_MANIFEST
    # ------------------------------------------------------------------

    def test_no_manifest_gives_block_and_review_when_no_checkpoint(self):
        mgr, _ = self._manager()
        decision = mgr.handle_integrity_failure(
            _no_manifest_result(),
            execution_id="e1",
            artifact_id="m:e1",
        )
        assert decision.recommended_action == "block_and_review"

    def test_no_manifest_gives_rollback_when_checkpoint_available(self):
        mgr, _ = self._manager()
        with tempfile.TemporaryDirectory() as td:
            from core.pipeline.checkpoints.manager import CheckpointManager
            ckpt_mgr = CheckpointManager(root_dir=td)
            ckpt_mgr.create(execution_id="e1", node_id="training", artifact={"x": 1})
            decision = mgr.handle_integrity_failure(
                _no_manifest_result(),
                execution_id="e1",
                artifact_id="m:e1",
                checkpoint_manager=ckpt_mgr,
            )
        assert decision.recommended_action == "rollback_to_trusted"

    # ------------------------------------------------------------------
    # Quarantine is metadata-only — no file deletion
    # ------------------------------------------------------------------

    def test_quarantine_does_not_delete_files(self, tmp_path):
        artifact = tmp_path / "model.joblib"
        artifact.write_bytes(b"precious-model")
        mgr, _ = self._manager()
        mgr.handle_integrity_failure(
            _failed_result(artifact_path=str(artifact)),
            execution_id="e1",
            artifact_id="m:e1",
        )
        # File must still exist — quarantine is metadata-only
        assert artifact.exists()

    def test_quarantine_record_is_created(self):
        mgr, _ = self._manager()
        mgr.handle_integrity_failure(
            _failed_result(),
            execution_id="e1",
            artifact_id="m:e1",
        )
        assert len(mgr.quarantine_records) == 1
        rec = mgr.quarantine_records[0]
        assert rec.artifact_id == "m:e1"
        assert rec.integrity_status == "failed"

    def test_quarantine_records_are_immutable_tuples(self):
        mgr, _ = self._manager()
        records = mgr.quarantine_records
        assert isinstance(records, tuple)

    # ------------------------------------------------------------------
    # Audit events are recorded
    # ------------------------------------------------------------------

    def test_audit_events_are_recorded(self):
        mgr, logger = self._manager()
        mgr.handle_integrity_failure(
            _failed_result(),
            execution_id="e1",
            artifact_id="m:e1",
        )
        # At minimum: INTEGRITY_CHECK_FAILED, ARTIFACT_QUARANTINED, SECURITY_AUDIT_RECORDED
        assert logger.count() >= 3

    def test_integrity_check_failed_event_recorded(self):
        mgr, logger = self._manager()
        mgr.handle_integrity_failure(
            _failed_result(),
            execution_id="e1",
            artifact_id="m:e1",
        )
        failed_events = logger.find_by_type(SecurityEventType.INTEGRITY_CHECK_FAILED)
        assert len(failed_events) == 1

    def test_artifact_quarantined_event_recorded(self):
        mgr, logger = self._manager()
        mgr.handle_integrity_failure(
            _failed_result(),
            execution_id="e1",
            artifact_id="m:e1",
        )
        q_events = logger.find_by_type(SecurityEventType.ARTIFACT_QUARANTINED)
        assert len(q_events) == 1

    def test_events_can_be_queried_by_execution(self):
        mgr, logger = self._manager()
        mgr.handle_integrity_failure(
            _failed_result(),
            execution_id="exec-special",
            artifact_id="m:e1",
        )
        found = logger.find_by_execution("exec-special")
        assert len(found) >= 1

    # ------------------------------------------------------------------
    # No destructive operations
    # ------------------------------------------------------------------

    def test_does_not_revoke_credentials(self):
        """SecurityRecoveryManager must not touch credentials."""
        mgr, _ = self._manager()
        decision = mgr.handle_integrity_failure(
            _failed_result(),
            execution_id="e1",
            artifact_id="m:e1",
        )
        # No method to revoke credentials exists on the manager
        assert not hasattr(mgr, "revoke_credentials")
        assert not hasattr(mgr, "rotate_api_key")

    def test_decision_never_says_delete_everything(self):
        mgr, _ = self._manager()
        decision = mgr.handle_integrity_failure(
            _failed_result(),
            execution_id="e1",
            artifact_id="m:e1",
        )
        bad_actions = {"delete_files", "wipe_production", "destroy_artifact"}
        assert decision.recommended_action not in bad_actions

    def test_all_decisions_require_human_review(self):
        """Every security decision must require human authorization."""
        mgr, _ = self._manager()
        for status in [IntegrityStatus.FAILED, IntegrityStatus.NO_MANIFEST]:
            r = IntegrityResult(
                valid=False, status=status, artifact_path="/p",
                algorithm="sha256", expected_checksum=None, actual_checksum=None,
                checked_at=datetime.now(timezone.utc), reason="test",
            )
            decision = mgr.handle_integrity_failure(r, execution_id="e", artifact_id="a")
            assert decision.requires_human_review is True, (
                f"Expected human_review=True for status {status}, "
                f"got action={decision.recommended_action}"
            )

    # ------------------------------------------------------------------
    # Trusted checkpoint selection
    # ------------------------------------------------------------------

    def test_select_trusted_checkpoint_emits_event(self):
        mgr, logger = self._manager()
        with tempfile.TemporaryDirectory() as td:
            from core.pipeline.checkpoints.manager import CheckpointManager
            ckpt_mgr = CheckpointManager(root_dir=td)
            c = ckpt_mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
            mgr.select_trusted_checkpoint([c], execution_id="e")
        found = logger.find_by_type(SecurityEventType.TRUSTED_CHECKPOINT_SELECTED)
        assert len(found) == 1

    def test_select_no_trusted_checkpoint_emits_rejected_event(self):
        mgr, logger = self._manager()
        with tempfile.TemporaryDirectory() as td:
            from core.pipeline.checkpoints.manager import CheckpointManager
            ckpt_mgr = CheckpointManager(root_dir=td)
            c = ckpt_mgr.create(
                execution_id="e", node_id="n", artifact={"x": 1},
                validation_status="failed",
            )
            mgr.select_trusted_checkpoint([c], execution_id="e")
        found = logger.find_by_type(SecurityEventType.UNTRUSTED_CHECKPOINT_REJECTED)
        assert len(found) == 1
