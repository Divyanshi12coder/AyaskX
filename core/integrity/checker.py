"""
core/integrity/checker.py
--------------------------
ArtifactIntegrityChecker — answers "Is this artifact trustworthy?"

Responsibilities:
  - Compute SHA-256 of artifact bytes.
  - Read integrity manifest from sidecar file.
  - Compare expected vs. actual checksum.
  - Return structured IntegrityResult (immutable).
  - Classify missing manifests vs. mismatch vs. missing artifact.

Does NOT:
  - Perform recovery.
  - Delete, quarantine, or move files.
  - Communicate with external services.

Manifest sidecar convention:
  Artifact:  <path>/<name>.joblib
  Manifest:  <path>/<name>.joblib.manifest.json

This avoids circular hashing: the checksum is computed over the raw
artifact bytes, not a file that already contains the checksum.

CheckpointTrust:
  The checker also provides assess_checkpoint_trust() which returns a
  CheckpointTrustReport — used by recovery logic to select a safe rollback.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from core.pipeline.checkpoints.manager import Checkpoint, CheckpointManager

_ALGORITHM = "sha256"
_ARTIFACT_VERSION = "1.0"
_CHUNK_SIZE = 65536  # 64 KiB — streaming SHA-256 for large artifacts


class ArtifactIntegrityChecker:
    """
    Computes and verifies SHA-256 integrity of ModelArtifact files.

    Usage
    -----
    checker = ArtifactIntegrityChecker()

    # Compute and write manifest at save time:
    manifest = checker.compute_manifest(artifact_path, artifact_obj)

    # Verify at load time:
    result = checker.verify(artifact_path)
    if not result.valid:
        raise ChecksumMismatchError(...)
    """

    # ------------------------------------------------------------------
    # Manifest path convention
    # ------------------------------------------------------------------

    @staticmethod
    def manifest_path(artifact_path: str | Path) -> Path:
        """Return the sidecar manifest path for a given artifact file."""
        p = Path(artifact_path)
        return p.parent / (p.name + ".manifest.json")

    # ------------------------------------------------------------------
    # Checksum computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_checksum(artifact_path: str | Path) -> str:
        """
        Compute SHA-256 of the artifact file bytes.

        Streams the file in 64 KiB chunks so large artifacts do not
        require loading entirely into memory.

        Raises
        ------
        FileNotFoundError if the artifact does not exist.
        """
        path = Path(artifact_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Artifact not found for checksum: {path}"
            )

        h = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Manifest creation (called at save time)
    # ------------------------------------------------------------------

    def create_manifest(
        self,
        artifact_path: str | Path,
        *,
        execution_id: str,
        dataset_fingerprint: str = "",
        checkpoint_id: str | None = None,
        model_name: str = "",
    ) -> IntegrityManifest:
        """
        Compute SHA-256 of the artifact and write a sidecar manifest.

        The checksum is computed AFTER the artifact is fully written,
        so there is no circular dependency.

        Returns the manifest object. Raises FileNotFoundError if the
        artifact file does not exist yet.
        """
        artifact_path = Path(artifact_path)
        checksum = self.compute_checksum(artifact_path)
        now = datetime.now(timezone.utc)

        artifact_id = (
            f"{model_name}:{execution_id}"
            if model_name
            else execution_id
        )

        manifest = IntegrityManifest(
            algorithm=_ALGORITHM,
            checksum=checksum,
            artifact_id=artifact_id,
            artifact_version=_ARTIFACT_VERSION,
            created_at=now.isoformat(),
            execution_id=execution_id,
            dataset_fingerprint=dataset_fingerprint,
            checkpoint_id=checkpoint_id,
        )

        manifest_path = self.manifest_path(artifact_path)
        _write_json_atomic(manifest_path, manifest.to_dict())

        return manifest

    # ------------------------------------------------------------------
    # Verification (called at load time)
    # ------------------------------------------------------------------

    def verify(
        self,
        artifact_path: str | Path,
        *,
        raise_on_failure: bool = False,
    ) -> IntegrityResult:
        """
        Verify the integrity of an artifact on disk.

        Returns IntegrityResult — always. Never raises unless
        raise_on_failure=True.

        Outcomes:
          PASSED         — checksum matches manifest
          FAILED         — checksum mismatch (artifact was modified)
          NO_MANIFEST    — artifact exists, manifest absent (legacy)
          ARTIFACT_MISSING — artifact not found on disk

        Parameters
        ----------
        artifact_path    : path to the joblib artifact file
        raise_on_failure : if True, raises ArtifactIntegrityError subtypes
                           instead of returning a FAILED result
        """
        path = Path(artifact_path)
        now = datetime.now(timezone.utc)

        # 1. Artifact must exist
        if not path.exists():
            result = IntegrityResult(
                valid=False,
                status=IntegrityStatus.ARTIFACT_MISSING,
                artifact_path=str(path),
                algorithm=_ALGORITHM,
                expected_checksum=None,
                actual_checksum=None,
                checked_at=now,
                reason=f"Artifact not found on disk: {path}",
            )
            if raise_on_failure:
                raise ArtifactIntegrityError(
                    result.reason, artifact_path=str(path)
                )
            return result

        # 2. Manifest must exist
        mpath = self.manifest_path(path)
        if not mpath.exists():
            result = IntegrityResult(
                valid=False,
                status=IntegrityStatus.NO_MANIFEST,
                artifact_path=str(path),
                algorithm=_ALGORITHM,
                expected_checksum=None,
                actual_checksum=None,
                checked_at=now,
                reason=(
                    f"No integrity manifest found for '{path.name}'. "
                    "This is a legacy artifact — integrity is unverified."
                ),
            )
            if raise_on_failure:
                raise MissingIntegrityMetadataError(
                    result.reason, artifact_path=str(path)
                )
            return result

        # 3. Load manifest
        try:
            raw = json.loads(mpath.read_text(encoding="utf-8"))
            manifest = IntegrityManifest.from_dict(raw)
        except Exception as exc:
            result = IntegrityResult(
                valid=False,
                status=IntegrityStatus.FAILED,
                artifact_path=str(path),
                algorithm=_ALGORITHM,
                expected_checksum=None,
                actual_checksum=None,
                checked_at=now,
                reason=f"Manifest could not be parsed: {exc}",
            )
            if raise_on_failure:
                raise ArtifactIntegrityError(result.reason, artifact_path=str(path))
            return result

        # 4. Compute actual checksum
        try:
            actual = self.compute_checksum(path)
        except Exception as exc:
            result = IntegrityResult(
                valid=False,
                status=IntegrityStatus.FAILED,
                artifact_path=str(path),
                algorithm=_ALGORITHM,
                expected_checksum=manifest.checksum,
                actual_checksum=None,
                checked_at=now,
                reason=f"Could not compute checksum: {exc}",
            )
            if raise_on_failure:
                raise ArtifactIntegrityError(result.reason, artifact_path=str(path))
            return result

        # 5. Compare
        if actual != manifest.checksum:
            result = IntegrityResult(
                valid=False,
                status=IntegrityStatus.FAILED,
                artifact_path=str(path),
                algorithm=_ALGORITHM,
                expected_checksum=manifest.checksum,
                actual_checksum=actual,
                checked_at=now,
                reason=(
                    f"Checksum mismatch for '{path.name}': "
                    f"expected {manifest.checksum[:12]}…, "
                    f"got {actual[:12]}…"
                ),
            )
            if raise_on_failure:
                raise ChecksumMismatchError(
                    result.reason,
                    expected=manifest.checksum,
                    actual=actual,
                    artifact_path=str(path),
                )
            return result

        # 6. All checks passed
        return IntegrityResult(
            valid=True,
            status=IntegrityStatus.PASSED,
            artifact_path=str(path),
            algorithm=_ALGORITHM,
            expected_checksum=manifest.checksum,
            actual_checksum=actual,
            checked_at=now,
            reason=f"Integrity verified: SHA-256 matches manifest for '{path.name}'.",
        )

    # ------------------------------------------------------------------
    # Checkpoint trust assessment
    # ------------------------------------------------------------------

    def assess_checkpoint_trust(
        self,
        checkpoint: "Checkpoint | None",
    ) -> CheckpointTrustReport:
        """
        Assess whether a checkpoint can be trusted as a recovery target.

        Trust levels (descending preference):
          integrity_verified  — structurally valid + data_hash non-empty
          structurally_valid  — required fields present
          exists              — checkpoint object present but invalid
          unavailable         — checkpoint is None

        A checkpoint is TRUSTED only if it is both structurally_valid
        and integrity_verified.

        Note: This does not verify against a SHA-256 file on disk because
        CheckpointManager stores data_hash of artifact content, not of its
        own metadata file. Full cryptographic checkpoint verification
        requires the original artifact bytes (future work).
        """
        if checkpoint is None:
            return CheckpointTrustReport(
                checkpoint_id=None,
                exists=False,
                structurally_valid=False,
                integrity_verified=False,
                trusted=False,
                trust_level="unavailable",
                reason="No checkpoint provided.",
            )

        cid = getattr(checkpoint, "checkpoint_id", None)
        exists = bool(cid)

        # Structural validity: required fields non-empty
        vstatus = getattr(checkpoint, "validation_status", "")
        data_hash = getattr(checkpoint, "data_hash", "")
        node_id = getattr(checkpoint, "node_id", "")

        structurally_valid = (
            bool(cid)
            and bool(vstatus)
            and bool(node_id)
            and vstatus == "passed"
        )

        # Integrity: data_hash non-empty (content was hashed at creation)
        integrity_verified = structurally_valid and bool(data_hash)

        trusted = structurally_valid and integrity_verified

        if trusted:
            trust_level = "integrity_verified"
            reason = (
                f"Checkpoint '{cid}' is trusted: "
                "validation_status=passed, data_hash present."
            )
        elif structurally_valid:
            trust_level = "structurally_valid"
            reason = (
                f"Checkpoint '{cid}' is structurally valid but "
                "data_hash is absent — integrity unverified."
            )
        elif exists:
            trust_level = "exists"
            reason = (
                f"Checkpoint '{cid}' exists but failed structural checks "
                f"(validation_status='{vstatus}')."
            )
        else:
            trust_level = "unavailable"
            reason = "Checkpoint has no valid checkpoint_id."

        return CheckpointTrustReport(
            checkpoint_id=cid,
            exists=exists,
            structurally_valid=structurally_valid,
            integrity_verified=integrity_verified,
            trusted=trusted,
            trust_level=trust_level,
            reason=reason,
        )

    def select_trusted_checkpoint(
        self,
        candidates: list["Checkpoint"],
    ) -> "Checkpoint | None":
        """
        From a list of checkpoints, return the most recent one that is
        both structurally valid and integrity verified.

        Prefers newer (later created_at) over older.
        A corrupted newer checkpoint does NOT override a trusted older one.
        Returns None if no trusted candidate is found.
        """
        trusted = []
        for ckpt in candidates:
            report = self.assess_checkpoint_trust(ckpt)
            if report.trusted:
                trusted.append(ckpt)

        if not trusted:
            return None

        return max(
            trusted,
            key=lambda c: getattr(c, "created_at", datetime.min),
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """
    Write JSON to path.  Uses a tmp file + rename for atomic write
    on platforms that support it (POSIX). On Windows, rename may fail
    if the target already exists, so we fall back to a direct write.
    """
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        suffix=".tmp",
        prefix=path.name + "_",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        # Atomic rename (POSIX) / fallback on Windows
        try:
            os.replace(tmp_path, path)
        except OSError:
            import shutil
            shutil.move(tmp_path, str(path))
    except Exception:
        # Clean up tmp file on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
