"""
core/integrity/models.py
------------------------
Immutable result models for artifact integrity checking.

Design principles:
- All result objects are frozen dataclasses (immutable after construction).
- No I/O or side effects in this module.
- JSON-serializable via to_dict().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class IntegrityStatus(str, Enum):
    """Outcome of an integrity check."""

    PASSED         = "passed"           # checksum matches
    FAILED         = "failed"           # checksum mismatch
    NO_MANIFEST    = "no_manifest"      # artifact present; manifest absent (legacy)
    ARTIFACT_MISSING = "artifact_missing"  # artifact file not on disk


@dataclass(frozen=True)
class IntegrityManifest:
    """
    Metadata written alongside a ModelArtifact at save time.

    The manifest is stored in a sidecar file (<artifact>.manifest.json)
    so the checksum is computed over the payload bytes, not over a file
    that already contains its own checksum (circular hashing avoided).

    Fields
    ------
    algorithm          : always "sha256" in this implementation
    checksum           : hex digest of the artifact bytes
    artifact_id        : stable identifier (model_name + execution_id)
    artifact_version   : version tag (currently "1.0")
    created_at         : UTC time the manifest was written
    execution_id       : training execution that produced the artifact
    dataset_fingerprint: sha fingerprint of the training data
    checkpoint_id      : checkpoint used during training (may be None)
    """

    algorithm: str
    checksum: str
    artifact_id: str
    artifact_version: str
    created_at: str           # ISO-8601 string for JSON-safe storage
    execution_id: str
    dataset_fingerprint: str
    checkpoint_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "checksum": self.checksum,
            "artifact_id": self.artifact_id,
            "artifact_version": self.artifact_version,
            "created_at": self.created_at,
            "execution_id": self.execution_id,
            "dataset_fingerprint": self.dataset_fingerprint,
            "checkpoint_id": self.checkpoint_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IntegrityManifest":
        return cls(
            algorithm=data["algorithm"],
            checksum=data["checksum"],
            artifact_id=data["artifact_id"],
            artifact_version=data.get("artifact_version", "1.0"),
            created_at=data["created_at"],
            execution_id=data["execution_id"],
            dataset_fingerprint=data.get("dataset_fingerprint", ""),
            checkpoint_id=data.get("checkpoint_id"),
        )


@dataclass(frozen=True)
class IntegrityResult:
    """
    Immutable result from ArtifactIntegrityChecker.

    Answers the question: "Is this artifact trustworthy?"

    Fields
    ------
    valid              : True ONLY when status == PASSED
    status             : IntegrityStatus constant
    artifact_path      : path to the artifact that was checked
    algorithm          : hash algorithm used ("sha256")
    expected_checksum  : checksum from the manifest (None if no manifest)
    actual_checksum    : checksum computed from artifact bytes (None if no artifact)
    checked_at         : UTC timestamp of the check
    reason             : human-readable explanation
    """

    valid: bool
    status: IntegrityStatus
    artifact_path: str
    algorithm: str
    expected_checksum: str | None
    actual_checksum: str | None
    checked_at: datetime
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "status": self.status.value,
            "artifact_path": self.artifact_path,
            "algorithm": self.algorithm,
            "expected_checksum": self.expected_checksum,
            "actual_checksum": self.actual_checksum,
            "checked_at": self.checked_at.isoformat(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CheckpointTrustReport:
    """
    Structured assessment of whether a checkpoint can be trusted
    as a recovery target.

    Levels of trust (in order of preference):
      integrity_verified → structurally_valid → exists → unavailable

    Fields
    ------
    checkpoint_id        : the checkpoint being assessed
    exists               : checkpoint metadata found in manager
    structurally_valid   : required fields present and non-empty
    integrity_verified   : data_hash matches stored content (if applicable)
    trusted              : True only when both structurally_valid AND
                           integrity_verified are True
    trust_level          : human-readable trust tier label
    reason               : explanation of the decision
    """

    checkpoint_id: str | None
    exists: bool
    structurally_valid: bool
    integrity_verified: bool
    trusted: bool
    trust_level: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "exists": self.exists,
            "structurally_valid": self.structurally_valid,
            "integrity_verified": self.integrity_verified,
            "trusted": self.trusted,
            "trust_level": self.trust_level,
            "reason": self.reason,
        }
