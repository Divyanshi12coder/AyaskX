"""
tests/test_checkpoint_trust.py
-------------------------------
Tests for checkpoint trust assessment and trusted checkpoint selection.

Verifies:
- Trusted checkpoints are correctly identified.
- Corrupted/invalid checkpoints are rejected.
- Newest TRUSTED checkpoint is selected (not just newest).
- RecoveryValidator.validate_artifact_integrity() works correctly.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone

import pytest

from core.integrity.checker import ArtifactIntegrityChecker
from core.integrity.models import IntegrityResult, IntegrityStatus
from core.pipeline.checkpoints.manager import CheckpointManager
from core.recovery.models import ValidationResult
from core.recovery.validator import RecoveryValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager() -> tuple[CheckpointManager, str]:
    """Returns (CheckpointManager, temp_dir_path) — caller must clean up."""
    import tempfile
    td = tempfile.mkdtemp()
    return CheckpointManager(root_dir=td), td


def _make_integrity_result(
    status: IntegrityStatus,
    reason: str = "test",
) -> IntegrityResult:
    return IntegrityResult(
        valid=(status == IntegrityStatus.PASSED),
        status=status,
        artifact_path="/some/artifact.joblib",
        algorithm="sha256",
        expected_checksum="aaa" if status == IntegrityStatus.PASSED else None,
        actual_checksum="aaa" if status == IntegrityStatus.PASSED else "bbb",
        checked_at=datetime.now(timezone.utc),
        reason=reason,
    )


# ---------------------------------------------------------------------------
# CheckpointManager — basic trust checks
# ---------------------------------------------------------------------------

class TestCheckpointManagerCreation:
    def test_checkpoint_has_validation_status_passed(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        ckpt = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
        assert ckpt.validation_status == "passed"

    def test_checkpoint_has_data_hash(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        ckpt = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
        assert bool(ckpt.data_hash)

    def test_checkpoint_has_checkpoint_id(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        ckpt = mgr.create(execution_id="e", node_id="n")
        assert bool(ckpt.checkpoint_id)


# ---------------------------------------------------------------------------
# ArtifactIntegrityChecker — checkpoint trust
# ---------------------------------------------------------------------------

class TestCheckpointTrustAssessment:
    def test_valid_checkpoint_is_trusted(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        ckpt = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
        checker = ArtifactIntegrityChecker()
        report = checker.assess_checkpoint_trust(ckpt)
        assert report.trusted is True
        assert report.trust_level == "integrity_verified"

    def test_none_is_unavailable(self):
        checker = ArtifactIntegrityChecker()
        report = checker.assess_checkpoint_trust(None)
        assert report.trusted is False
        assert report.trust_level == "unavailable"
        assert report.exists is False

    def test_failed_validation_status_not_trusted(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        ckpt = mgr.create(
            execution_id="e", node_id="n",
            artifact={"x": 1},
            validation_status="failed",
        )
        checker = ArtifactIntegrityChecker()
        report = checker.assess_checkpoint_trust(ckpt)
        assert report.trusted is False

    def test_empty_data_hash_not_integrity_verified(self, tmp_path):
        """Checkpoint with no artifact → no data_hash → integrity unverified."""
        mgr = CheckpointManager(root_dir=tmp_path)
        ckpt = mgr.create(execution_id="e", node_id="n")  # no artifact → empty hash
        checker = ArtifactIntegrityChecker()
        report = checker.assess_checkpoint_trust(ckpt)
        # data_hash="" → integrity_verified=False
        # But still structurally valid
        if not ckpt.data_hash:
            assert report.integrity_verified is False
            assert report.trusted is False

    def test_trust_report_is_immutable(self, tmp_path):
        from dataclasses import FrozenInstanceError
        mgr = CheckpointManager(root_dir=tmp_path)
        ckpt = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
        checker = ArtifactIntegrityChecker()
        report = checker.assess_checkpoint_trust(ckpt)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            report.trusted = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# select_trusted_checkpoint — newest trusted wins
# ---------------------------------------------------------------------------

class TestSelectTrustedCheckpoint:
    def test_selects_newest_trusted(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        c1 = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
        c2 = mgr.create(execution_id="e", node_id="n", artifact={"x": 2})
        checker = ArtifactIntegrityChecker()
        best = checker.select_trusted_checkpoint([c1, c2])
        assert best is not None
        assert best.checkpoint_id == c2.checkpoint_id

    def test_corrupted_newer_does_not_override_older_trusted(self, tmp_path):
        """
        A failed validation_status checkpoint must not beat a trusted one,
        even if it is newer.
        """
        mgr = CheckpointManager(root_dir=tmp_path)
        c_good = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
        c_bad = mgr.create(
            execution_id="e", node_id="n", artifact={"x": 2},
            validation_status="failed",
        )
        checker = ArtifactIntegrityChecker()
        best = checker.select_trusted_checkpoint([c_good, c_bad])
        assert best is not None
        assert best.checkpoint_id == c_good.checkpoint_id

    def test_returns_none_when_no_trusted(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        c = mgr.create(
            execution_id="e", node_id="n",
            artifact={"x": 1},
            validation_status="failed",
        )
        checker = ArtifactIntegrityChecker()
        best = checker.select_trusted_checkpoint([c])
        assert best is None

    def test_returns_none_for_empty_list(self):
        checker = ArtifactIntegrityChecker()
        assert checker.select_trusted_checkpoint([]) is None

    def test_single_trusted_checkpoint_is_returned(self, tmp_path):
        mgr = CheckpointManager(root_dir=tmp_path)
        c = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
        checker = ArtifactIntegrityChecker()
        best = checker.select_trusted_checkpoint([c])
        assert best is not None
        assert best.checkpoint_id == c.checkpoint_id


# ---------------------------------------------------------------------------
# RecoveryValidator.validate_artifact_integrity()
# ---------------------------------------------------------------------------

class TestRecoveryValidatorArtifactIntegrity:
    def _validator(self) -> RecoveryValidator:
        return RecoveryValidator()

    def test_passed_integrity_validates_successfully(self, tmp_path):
        f = tmp_path / "model.joblib"
        f.write_bytes(b"model-content")
        v = self._validator()
        result_ir = _make_integrity_result(IntegrityStatus.PASSED)
        # Override path to existing file
        result_ir = IntegrityResult(
            valid=True, status=IntegrityStatus.PASSED,
            artifact_path=str(f), algorithm="sha256",
            expected_checksum="aaa", actual_checksum="aaa",
            checked_at=datetime.now(timezone.utc), reason="OK",
        )
        val = v.validate_artifact_integrity(str(f), result_ir)
        assert val.passed is True

    def test_missing_artifact_fails_validation(self, tmp_path):
        v = self._validator()
        missing = str(tmp_path / "does_not_exist.joblib")
        result_ir = _make_integrity_result(IntegrityStatus.PASSED)
        val = v.validate_artifact_integrity(missing, result_ir)
        assert val.passed is False
        assert "artifact_exists_on_disk" in val.failures

    def test_failed_integrity_fails_validation(self, tmp_path):
        f = tmp_path / "model.joblib"
        f.write_bytes(b"model")
        v = self._validator()
        result_ir = _make_integrity_result(IntegrityStatus.FAILED, reason="Mismatch")
        val = v.validate_artifact_integrity(str(f), result_ir)
        assert val.passed is False
        assert "integrity_check_passed" in val.failures

    def test_no_integrity_result_fails(self, tmp_path):
        f = tmp_path / "model.joblib"
        f.write_bytes(b"model")
        v = self._validator()
        val = v.validate_artifact_integrity(str(f), None)
        assert val.passed is False
        assert "integrity_check_was_performed" in val.failures

    def test_none_path_fails(self):
        v = self._validator()
        val = v.validate_artifact_integrity(None, None)
        assert val.passed is False
        assert "artifact_path_provided" in val.failures

    def test_no_manifest_is_acceptable(self, tmp_path):
        """Legacy artifacts (NO_MANIFEST) should pass the validation gate."""
        f = tmp_path / "legacy.joblib"
        f.write_bytes(b"legacy")
        v = self._validator()
        result_ir = _make_integrity_result(IntegrityStatus.NO_MANIFEST)
        result_ir = IntegrityResult(
            valid=False, status=IntegrityStatus.NO_MANIFEST,
            artifact_path=str(f), algorithm="sha256",
            expected_checksum=None, actual_checksum=None,
            checked_at=datetime.now(timezone.utc), reason="No manifest.",
        )
        val = v.validate_artifact_integrity(str(f), result_ir)
        # NO_MANIFEST is treated as acceptable (legacy backward-compat)
        assert "integrity_check_passed" not in val.failures

    def test_validation_result_is_immutable(self, tmp_path):
        from dataclasses import FrozenInstanceError
        f = tmp_path / "model.joblib"
        f.write_bytes(b"model")
        v = self._validator()
        val = v.validate_artifact_integrity(str(f), None)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            val.passed = True  # type: ignore[misc]
