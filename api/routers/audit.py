"""api/routers/audit.py — Security audit endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from api.dependencies import get_audit_logger, get_execution_store
from api.schemas.common import ApiResponse

router = APIRouter(prefix="/v1", tags=["Audit"])


@router.get("/audit/events")
def list_audit_events(
    execution_id: str | None = Query(default=None),
    audit_logger=Depends(get_audit_logger),
):
    events = audit_logger.events()
    if execution_id:
        events = tuple(e for e in events if getattr(e, "execution_id", None) == execution_id)
    return ApiResponse.ok([e.to_dict() if hasattr(e, "to_dict") else vars(e) for e in events])


@router.get("/audit/events/{event_id}")
def get_audit_event(
    event_id: str,
    audit_logger=Depends(get_audit_logger),
):
    for e in audit_logger.events():
        if getattr(e, "event_id", None) == event_id:
            return ApiResponse.ok(e.to_dict() if hasattr(e, "to_dict") else vars(e))
    raise HTTPException(status_code=404, detail=f"Audit event '{event_id}' not found")


@router.get("/pipelines/{execution_id}/audit")
def get_execution_audit(
    execution_id: str,
    store=Depends(get_execution_store),
    audit_logger=Depends(get_audit_logger),
):
    if not store.exists(execution_id):
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    events = tuple(
        e for e in audit_logger.events()
        if getattr(e, "execution_id", None) == execution_id
    )
    return ApiResponse.ok(
        [e.to_dict() if hasattr(e, "to_dict") else vars(e) for e in events],
        execution_id=execution_id,
    )
