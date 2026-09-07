"""
core/integrity/errors.py
------------------------
Dedicated exception hierarchy for artifact integrity failures.

Design:
- ArtifactIntegrityError is the base class.
- Each subclass is distinguishable from standard FileNotFoundError,
  schema mismatches, and execution errors.
- Integrates cleanly with FaultType.CORRUPTED_ARTIFACT.
- All exceptions carry structured context for audit records.
"""

from __future__ import annotations


class ArtifactIntegrityError(Exception):
    """
    Base class for all artifact integrity failures in AyaskX.

    Distinguishable from:
    - FileNotFoundError    (missing artifact)
    - TypeError / schema   (schema mismatch)
    - RuntimeError         (execution error)

    FaultDetector maps this to FaultType.CORRUPTED_ARTIFACT.
    """

    def __init__(
        self,
        message: str,
        artifact_path: str | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.artifact_path = artifact_path
        self.context: dict = context or {}


class ChecksumMismatchError(ArtifactIntegrityError):
    """
    Raised when the computed SHA-256 of an artifact does not match
    the stored checksum in its integrity manifest.

    This is a HIGH/CRITICAL integrity event — the artifact has been
    modified (deliberately or accidentally) since it was saved.

    Fields:
        expected  : checksum recorded in the manifest at save-time
        actual    : checksum computed from the artifact on disk now
    """

    def __init__(
        self,
        message: str,
        expected: str,
        actual: str,
        artifact_path: str | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(message, artifact_path=artifact_path, context=context)
        self.expected = expected
        self.actual = actual


class MissingIntegrityMetadataError(ArtifactIntegrityError):
    """
    Raised when an artifact exists on disk but no integrity manifest
    was found alongside it.

    This is NOT a fatal error for legacy artifacts. Callers must
    decide whether to accept unverified artifacts.
    """
