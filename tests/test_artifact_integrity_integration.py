"""
tests/test_artifact_integrity_integration.py
---------------------------------------------
Integration tests for ModelArtifact save/load with SHA-256 integrity.

Verifies:
- save() writes sidecar manifest.
- load() verifies manifest by default.
- Corrupted artifact cannot be loaded as trusted.
- Legacy artifacts (no manifest) load as 'unverified', not rejected.
- integrity_verified property reflects result.
- strict=True raises ChecksumMismatchError on mismatch.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.inference.engine import ModelArtifact
from core.integrity.checker import ArtifactIntegrityChecker
from core.integrity.errors import ChecksumMismatchError
from core.integrity.models import IntegrityStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_artifact(
    model_name: str = "rf",
    execution_id: str = "exec-001",
    task_type: str = "classification",
) -> ModelArtifact:
    """Create a minimal ModelArtifact with a real (picklable) sklearn pipeline."""
    from sklearn.dummy import DummyClassifier
    from sklearn.pipeline import Pipeline as SkPipeline
    import numpy as np

    pipeline = SkPipeline([("clf", DummyClassifier(strategy="most_frequent"))])
    # Fit it on tiny data so it's in a complete state
    pipeline.fit(np.array([[1], [2], [3]]), [0, 1, 0])

    return ModelArtifact(
        model_name=model_name,
        task_type=task_type,
        execution_id=execution_id,
        pipeline=pipeline,
        feature_columns=["a", "b", "c"],
        target_column="label",
        metrics={"accuracy": 0.95},
        validation_strategy="random_holdout",
        dataset_fingerprint="sha:100x3:abc",
        checkpoint_id="ckpt-001",
    )



# ---------------------------------------------------------------------------
# save() — creates sidecar manifest
# ---------------------------------------------------------------------------

class TestModelArtifactSave:
    def test_save_creates_manifest_sidecar(self, tmp_path):
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        checker = ArtifactIntegrityChecker()
        manifest_path = checker.manifest_path(path)
        assert manifest_path.exists()

    def test_save_returns_path(self, tmp_path):
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        result = artifact.save(path)
        assert result == path
        assert result.exists()

    def test_save_manifest_contains_execution_id(self, tmp_path):
        import json
        artifact = _make_artifact(execution_id="exec-XYZ")
        path = tmp_path / "model.joblib"
        artifact.save(path)
        checker = ArtifactIntegrityChecker()
        manifest_data = json.loads(checker.manifest_path(path).read_text())
        assert manifest_data["execution_id"] == "exec-XYZ"

    def test_save_manifest_contains_checksum(self, tmp_path):
        import json
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        checker = ArtifactIntegrityChecker()
        manifest_data = json.loads(checker.manifest_path(path).read_text())
        assert len(manifest_data["checksum"]) == 64  # sha256 hex

    def test_save_manifest_checksum_algorithm_is_sha256(self, tmp_path):
        import json
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        checker = ArtifactIntegrityChecker()
        manifest_data = json.loads(checker.manifest_path(path).read_text())
        assert manifest_data["algorithm"] == "sha256"


# ---------------------------------------------------------------------------
# load() — verifies integrity by default
# ---------------------------------------------------------------------------

class TestModelArtifactLoad:
    def test_load_valid_artifact_succeeds(self, tmp_path):
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path)
        assert loaded.model_name == "rf"

    def test_load_sets_integrity_status_passed(self, tmp_path):
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path)
        assert loaded.integrity_status == IntegrityStatus.PASSED.value

    def test_integrity_verified_property_true_after_clean_load(self, tmp_path):
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path)
        assert loaded.integrity_verified is True

    def test_corrupted_artifact_loads_as_failed(self, tmp_path):
        """A modified manifest checksum marks the artifact as FAILED on load."""
        import json
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        # Corrupt only the manifest checksum — the artifact bytes stay valid
        # so joblib can still load it, but integrity check will fail.
        checker = ArtifactIntegrityChecker()
        sidecar = checker.manifest_path(path)
        data = json.loads(sidecar.read_text())
        data["checksum"] = "f" * 64   # wrong checksum
        sidecar.write_text(json.dumps(data))
        loaded = ModelArtifact.load(path)
        assert loaded.integrity_status == IntegrityStatus.FAILED.value
        assert loaded.integrity_verified is False


    def test_strict_raises_on_corrupted_artifact(self, tmp_path):
        """strict=True must raise ChecksumMismatchError for tampered artifact."""
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        # Corrupt the manifest checksum (safest way to test without breaking joblib)
        import json
        checker = ArtifactIntegrityChecker()
        sidecar = checker.manifest_path(path)
        data = json.loads(sidecar.read_text())
        data["checksum"] = "b" * 64
        sidecar.write_text(json.dumps(data))
        with pytest.raises(ChecksumMismatchError):
            ModelArtifact.load(path, strict=True)

    def test_legacy_artifact_loads_as_unverified(self, tmp_path):
        """Artifacts without a manifest load with NO_MANIFEST status, not rejected."""
        import joblib
        artifact = _make_artifact()
        path = tmp_path / "legacy.joblib"
        # Save without calling save() to skip manifest creation
        joblib.dump(artifact, path)
        loaded = ModelArtifact.load(path)
        assert loaded.integrity_status == IntegrityStatus.NO_MANIFEST.value
        assert loaded.integrity_verified is False
        # But it loaded successfully — backward-compatible
        assert loaded.model_name == "rf"

    def test_verify_integrity_false_skips_check(self, tmp_path):
        """verify_integrity=False skips the check and marks artifact as 'unverified'."""
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path, verify_integrity=False)
        assert loaded.integrity_status == "unverified"
        assert loaded.integrity_verified is False

    def test_integrity_state_is_observable(self, tmp_path):
        """integrity_status must be accessible as a string attribute."""
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path)
        assert isinstance(loaded.integrity_status, str)
        assert hasattr(loaded, "integrity_verified")


# ---------------------------------------------------------------------------
# End-to-end: save → load → verify
# ---------------------------------------------------------------------------

class TestArtifactSaveLoadCycle:
    def test_save_load_preserves_model_name(self, tmp_path):
        artifact = _make_artifact(model_name="gradient_boosting")
        path = tmp_path / "gb.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path)
        assert loaded.model_name == "gradient_boosting"

    def test_save_load_preserves_execution_id(self, tmp_path):
        artifact = _make_artifact(execution_id="exec-UNIQUE-42")
        path = tmp_path / "model.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path)
        assert loaded.execution_id == "exec-UNIQUE-42"

    def test_save_load_preserves_metrics(self, tmp_path):
        artifact = _make_artifact()
        artifact.metrics["f1"] = 0.88
        path = tmp_path / "model.joblib"
        artifact.save(path)
        loaded = ModelArtifact.load(path)
        assert loaded.metrics["f1"] == pytest.approx(0.88)

    def test_checker_verify_after_clean_save(self, tmp_path):
        artifact = _make_artifact()
        path = tmp_path / "model.joblib"
        artifact.save(path)
        checker = ArtifactIntegrityChecker()
        result = checker.verify(path)
        assert result.valid is True
        assert result.status == IntegrityStatus.PASSED
