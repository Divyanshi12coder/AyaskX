"""api/routers/health.py — /health and /ready endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter

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
        return {"status": "ready", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"Not ready: {exc}")
