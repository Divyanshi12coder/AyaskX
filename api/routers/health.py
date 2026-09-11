"""api/routers/health.py — /health and /ready endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

router = APIRouter(tags=["Health"])

_STARTED_AT = datetime.now(timezone.utc).isoformat()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ayaskx-api",
        "started_at": _STARTED_AT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
def ready():
    try:
        from core.platform.orchestrator import AyaskXOrchestrator  # noqa: F401
        from core.database.connection import get_session, init_db

        # A file merely existing is not evidence that the configured database
        # is reachable. Initialise idempotently, then issue a cheap query.
        init_db()
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Not ready: {exc}")
