"""
tests/test_integrity.py
-----------------------
Tests for core/integrity/: ArtifactIntegrityChecker, IntegrityManifest,
IntegrityResult, CheckpointTrustReport, and all error types.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.integrity.checker import ArtifactIntegrityChecker
from core.integrity.errors import (
    ArtifactIntegrityError,
    ChecksumMismatchError,
    MissingIntegrityMetadataError,
)
from core.integrity.models import (
    CheckpointTrustReport,
    IntegrityManifest,
    IntegrityResult,
    IntegrityStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_artifact(path: Path, content: bytes = b"dummy-model-bytes") -> Path:
    path.write_bytes(content)
    return path


def _make_checker() -> ArtifactIntegrityChecker:
    return ArtifactIntegrityChecker()


# ---------------------------------------------------------------------------
# IntegrityManifest
# ---------------------------------------------------------------------------

class TestIntegrityManifest:
    def test_to_dict_is_json_serializable(self):
        m = IntegrityManifest(
            algorithm="sha256",
            checksum="abc123",
            artifact_id="model:exec",
            artifact_version="1.0",
            created_at=datetime.now(timezone.utc).isoformat(),
            execution_id="exec-001",
            dataset_fingerprint="sha:500x43:abc",
            checkpoint_id="ckpt-1",
        )
        d = m.to_dict()
        assert json.dumps(d)  # must not raise
        assert d["algorithm"] == "sha256"
        assert d["checksum"] == "abc123"

    def test_from_dict_roundtrip(self):
        m = IntegrityManifest(
            algorithm="sha256",
            checksum="deadbeef",
            artifact_id="model:exec",
            artifact_version="1.0",
            created_at="2024-01-01T00:00:00+00:00",
            execution_id="exec-001",
            dataset_fingerprint="sha:100x10:ff",
            checkpoint_id=None,
        )
        d = m.to_dict()
        m2 = IntegrityManifest.from_dict(d)
        assert m2.checksum == m.checksum
        assert m2.checkpoint_id is None

    def test_immutable(self):
        m = IntegrityManifest(
            algorithm="sha256", checksum="x", artifact_id="a",
            artifact_version="1.0", created_at="now",
            execution_id="e", dataset_fingerprint="f", checkpoint_id=None,
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            m.checksum = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IntegrityResult
# ---------------------------------------------------------------------------

class TestIntegrityResult:
    def test_immutable(self):
        r = IntegrityResult(
            valid=True,
            status=IntegrityStatus.PASSED,
            artifact_path="/some/path",
            algorithm="sha256",
            expected_checksum="aaa",
            actual_checksum="aaa",
            checked_at=datetime.now(timezone.utc),
            reason="OK",
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            r.valid = False  # type: ignore[misc]

    def test_to_dict_json_safe(self):
        r = IntegrityResult(
            valid=False,
            status=IntegrityStatus.FAILED,
            artifact_path="/p",
            algorithm="sha256",
            expected_checksum="111",
            actual_checksum="222",
            checked_at=datetime.now(timezone.utc),
            reason="Mismatch",
        )
        d = r.to_dict()
        assert json.dumps(d)
        assert d["valid"] is False
        assert d["status"] == "failed"


# ---------------------------------------------------------------------------
# ArtifactIntegrityChecker — checksum
# ---------------------------------------------------------------------------

class TestChecksumComputation:
    def test_deterministic_sha256(self, tmp_path):
        f = tmp_path / "artifact.joblib"
        _write_artifact(f, b"hello-model")
        c = _make_checker()
        h1 = c.compute_checksum(f)
        h2 = c.compute_checksum(f)
        assert h1 == h2

    def test_different_content_different_checksum(self, tmp_path):
        f1 = tmp_path / "a.joblib"
        f2 = tmp_path / "b.joblib"
        _write_artifact(f1, b"model-A")
        _write_artifact(f2, b"model-B")
        c = _make_checker()
        assert c.compute_checksum(f1) != c.compute_checksum(f2)

    def test_checksum_matches_manual_sha256(self, tmp_path):
        content = b"reference-content-12345"
        f = tmp_path / "ref.joblib"
        _write_artifact(f, content)
        expected = hashlib.sha256(content).hexdigest()
        actual = _make_checker().compute_checksum(f)
        assert actual == expected

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _make_checker().compute_checksum(tmp_path / "nonexistent.joblib")

    def test_checksum_changes_when_content_changes(self, tmp_path):
        f = tmp_path / "model.joblib"
        _write_artifact(f, b"original")
        c = _make_checker()
        h1 = c.compute_checksum(f)
        f.write_bytes(b"modified")
        h2 = c.compute_checksum(f)
        assert h1 != h2


# ---------------------------------------------------------------------------
# ArtifactIntegrityChecker — manifest creation and verification
# ---------------------------------------------------------------------------

class TestManifestCreationAndVerification:
    def test_create_manifest_writes_sidecar(self, tmp_path):
        f = tmp_path / "model.joblib"
        _write_artifact(f)
        c = _make_checker()
        manifest = c.create_manifest(
            f, execution_id="exec-001",
            dataset_fingerprint="sha:100x5:abc",
            checkpoint_id="ckpt-1",
            model_name="rf",
        )
        sidecar = c.manifest_path(f)
        assert sidecar.exists()
        assert manifest.algorithm == "sha256"
        assert len(manifest.checksum) == 64  # sha256 hex = 64 chars

    def test_verify_passes_on_valid_artifact(self, tmp_path):
        f = tmp_path / "model.joblib"
        _write_artifact(f, b"valid-content")
        c = _make_checker()
        c.create_manifest(f, execution_id="e1")
        result = c.verify(f)
        assert result.valid is True
        assert result.status == IntegrityStatus.PASSED
        assert result.expected_checksum == result.actual_checksum

    def test_verify_fails_on_modified_artifact(self, tmp_path):
        f = tmp_path / "model.joblib"
        _write_artifact(f, b"original")
        c = _make_checker()
        c.create_manifest(f, execution_id="e1")
        # Tamper
        f.write_bytes(b"tampered!!!")
        result = c.verify(f)
        assert result.valid is False
        assert result.status == IntegrityStatus.FAILED
        assert result.expected_checksum != result.actual_checksum

    def test_verify_wrong_checksum_in_manifest(self, tmp_path):
        f = tmp_path / "model.joblib"
        _write_artifact(f, b"real-content")
        c = _make_checker()
        c.create_manifest(f, execution_id="e1")
        # Corrupt the manifest
        sidecar = c.manifest_path(f)
        data = json.loads(sidecar.read_text())
        data["checksum"] = "a" * 64
        sidecar.write_text(json.dumps(data))
        result = c.verify(f)
        assert result.valid is False
        assert result.status == IntegrityStatus.FAILED

    def test_verify_missing_manifest_returns_no_manifest(self, tmp_path):
        f = tmp_path / "legacy.joblib"
        _write_artifact(f)
        result = _make_checker().verify(f)
        assert result.valid is False
        assert result.status == IntegrityStatus.NO_MANIFEST
        assert result.expected_checksum is None

    def test_verify_missing_artifact_returns_artifact_missing(self, tmp_path):
        f = tmp_path / "gone.joblib"
        result = _make_checker().verify(f)
        assert result.valid is False
        assert result.status == IntegrityStatus.ARTIFACT_MISSING

    def test_verify_raise_on_failure_raises_checksum_mismatch(self, tmp_path):
        f = tmp_path / "model.joblib"
        _write_artifact(f, b"original")
        c = _make_checker()
        c.create_manifest(f, execution_id="e1")
        f.write_bytes(b"tampered")
        with pytest.raises(ChecksumMismatchError) as exc_info:
            c.verify(f, raise_on_failure=True)
        assert exc_info.value.expected != exc_info.value.actual

    def test_verify_raise_on_failure_raises_missing_manifest(self, tmp_path):
        f = tmp_path / "legacy.joblib"
        _write_artifact(f)
        with pytest.raises(MissingIntegrityMetadataError):
            _make_checker().verify(f, raise_on_failure=True)

    def test_manifest_metadata_serializable(self, tmp_path):
        f = tmp_path / "model.joblib"
        _write_artifact(f)
        c = _make_checker()
        m = c.create_manifest(f, execution_id="e1", model_name="rf")
        assert json.dumps(m.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------

class TestErrorHierarchy:
    def test_checksum_mismatch_is_integrity_error(self):
        exc = ChecksumMismatchError("bad", expected="aaa", actual="bbb")
        assert isinstance(exc, ArtifactIntegrityError)
        assert exc.expected == "aaa"
        assert exc.actual == "bbb"

    def test_missing_manifest_is_integrity_error(self):
        exc = MissingIntegrityMetadataError("no manifest")
        assert isinstance(exc, ArtifactIntegrityError)

    def test_base_integrity_error_has_context(self):
        exc = ArtifactIntegrityError("msg", artifact_path="/p", context={"k": "v"})
        assert exc.artifact_path == "/p"
        assert exc.context["k"] == "v"

    def test_distinguishable_from_file_not_found(self):
        exc = ArtifactIntegrityError("integrity")
        assert not isinstance(exc, FileNotFoundError)

    def test_distinguishable_from_type_error(self):
        exc = ArtifactIntegrityError("integrity")
        assert not isinstance(exc, TypeError)


# ---------------------------------------------------------------------------
# CheckpointTrustReport
# ---------------------------------------------------------------------------

class TestCheckpointTrustReport:
    def test_immutable(self):
        r = CheckpointTrustReport(
            checkpoint_id="c1", exists=True, structurally_valid=True,
            integrity_verified=True, trusted=True,
            trust_level="integrity_verified", reason="ok",
        )
        with pytest.raises((FrozenInstanceError, AttributeError)):
            r.trusted = False  # type: ignore[misc]

    def test_to_dict_json_safe(self):
        r = CheckpointTrustReport(
            checkpoint_id="c1", exists=True, structurally_valid=True,
            integrity_verified=True, trusted=True,
            trust_level="integrity_verified", reason="ok",
        )
        assert json.dumps(r.to_dict())


# ---------------------------------------------------------------------------
# ArtifactIntegrityChecker — checkpoint trust
# ---------------------------------------------------------------------------

class TestCheckpointTrustAssessment:
    def _make_checkpoint(self, **kwargs):
        from dataclasses import dataclass
        from datetime import datetime, timezone

        @dataclass(frozen=True)
        class FakeCheckpoint:
            checkpoint_id: str = "ckpt-1"
            execution_id: str = "exec-001"
            node_id: str = "training"
            created_at: datetime = None
            node_version: str = "1.0"
            data_hash: str = "abc123"
            input_schema: dict = None
            output_schema: dict = None
            artifact_path: str | None = None
            validation_status: str = "passed"
            metadata: dict = None

            def __post_init__(self):
                object.__setattr__(self, 'created_at', datetime.now(timezone.utc))
                object.__setattr__(self, 'input_schema', {})
                object.__setattr__(self, 'output_schema', {})
                object.__setattr__(self, 'metadata', {})

        ckpt = FakeCheckpoint(**kwargs)
        return ckpt

    def test_trusted_checkpoint_passes(self):
        ckpt = self._make_checkpoint()
        report = _make_checker().assess_checkpoint_trust(ckpt)
        assert report.trusted is True
        assert report.trust_level == "integrity_verified"

    def test_none_checkpoint_is_unavailable(self):
        report = _make_checker().assess_checkpoint_trust(None)
        assert report.trusted is False
        assert report.trust_level == "unavailable"
        assert report.exists is False

    def test_failed_validation_status_not_trusted(self):
        ckpt = self._make_checkpoint(validation_status="failed")
        report = _make_checker().assess_checkpoint_trust(ckpt)
        assert report.trusted is False
        assert report.structurally_valid is False

    def test_missing_data_hash_not_integrity_verified(self):
        ckpt = self._make_checkpoint(data_hash="")
        report = _make_checker().assess_checkpoint_trust(ckpt)
        assert report.integrity_verified is False
        assert report.trusted is False

    def test_select_trusted_prefers_newer(self):
        from datetime import timedelta

        @dataclass_from_fields()
        class FakeCkpt:
            pass

        # Use real Checkpoint from CheckpointManager
        import tempfile
        from core.pipeline.checkpoints.manager import CheckpointManager
        with tempfile.TemporaryDirectory() as td:
            mgr = CheckpointManager(root_dir=td)
            c1 = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
            c2 = mgr.create(execution_id="e", node_id="n", artifact={"x": 2})
        checker = _make_checker()
        best = checker.select_trusted_checkpoint([c1, c2])
        assert best is not None
        assert best.checkpoint_id == c2.checkpoint_id

    def test_select_trusted_rejects_corrupted_newer(self):
        """A corrupted newer checkpoint must not override a trusted older one."""
        import tempfile
        from core.pipeline.checkpoints.manager import CheckpointManager
        with tempfile.TemporaryDirectory() as td:
            mgr = CheckpointManager(root_dir=td)
            c_old = mgr.create(execution_id="e", node_id="n", artifact={"x": 1})
            c_bad = mgr.create(
                execution_id="e", node_id="n", artifact={"x": 2},
                validation_status="failed",
            )
        checker = _make_checker()
        best = checker.select_trusted_checkpoint([c_old, c_bad])
        assert best is not None
        assert best.checkpoint_id == c_old.checkpoint_id


def dataclass_from_fields():
    """Stub decorator — not actually used, real checkpoints come from CheckpointManager."""
    def inner(cls):
        return cls
    return inner
