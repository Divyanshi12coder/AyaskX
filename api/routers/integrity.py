"""Integrity verification over server-managed model artifacts only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.config import Settings, get_settings
from api.schemas.common import ApiResponse

router = APIRouter(prefix="/v1/integrity", tags=["Integrity"])


@router.get("/artifacts")
def list_artifact_integrity(
    execution_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    """Verify artifacts under the configured artifact root.

    Paths come exclusively from server configuration and cannot be supplied by
    the caller, preventing path traversal through an integrity endpoint.
    """
    from core.integrity.checker import ArtifactIntegrityChecker

    checker = ArtifactIntegrityChecker()
    artifacts = []
    for path in sorted(settings.artifact_root.glob("*.joblib")):
        if execution_id and not path.name.startswith(f"{execution_id}_"):
            continue
        result = checker.verify(path)
        artifacts.append({
            "artifact_name": path.name,
            "artifact_path": path.name,
            "execution_id": path.name.split("_", 1)[0],
            "status": result.status.value,
            "valid": result.valid,
            "reason": result.reason,
            "expected_checksum": result.expected_checksum,
            "actual_checksum": result.actual_checksum,
        })
    return ApiResponse.ok(artifacts, execution_id=execution_id)
