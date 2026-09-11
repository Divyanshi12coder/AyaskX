"""Operational system-status endpoints for the administration console."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text

from api.config import Settings, get_settings
from api.dependencies import get_dataset_store, get_execution_store
from api.schemas.common import ApiResponse

router = APIRouter(prefix="/v1/system", tags=["System"])


@router.get("/status")
def system_status(
    settings: Settings = Depends(get_settings),
    dataset_store=Depends(get_dataset_store),
    execution_store=Depends(get_execution_store),
):
    """Return non-sensitive, observed operational state for administrators."""
    database_ready = False
    database_dialect = None
    try:
        from core.database.connection import engine, get_session, init_db

        init_db()
        with get_session() as session:
            session.execute(text("SELECT 1"))
        database_ready = True
        database_dialect = engine.dialect.name
    except Exception:
        # Status endpoints report a degraded component rather than leaking the
        # connection error or credentials to browser clients.
        pass

    def _directory_ready(path):
        return path.exists() and path.is_dir()

    return ApiResponse.ok({
        "api": {"status": "ready", "version": "1.0.0"},
        "database": {"status": "ready" if database_ready else "unavailable", "dialect": database_dialect},
        "storage": {
            "uploads_ready": _directory_ready(settings.upload_tmp_root),
            "artifacts_ready": _directory_ready(settings.artifact_root),
            "checkpoints_ready": _directory_ready(settings.checkpoint_root),
            "execution_store_ready": _directory_ready(settings.store_root),
        },
        "counts": {
            "datasets": len(dataset_store.list_all()),
            "executions": len(execution_store.list_all()),
        },
        "runtime": {
            "execution_mode": "in_process_background_thread",
            "authentication": "not_configured",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
