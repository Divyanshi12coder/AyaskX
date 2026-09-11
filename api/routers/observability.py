"""Read-only operational summaries derived from persisted execution records."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_execution_store
from api.schemas.common import ApiResponse

router = APIRouter(prefix="/v1/observability", tags=["Observability"])


@router.get("/summary")
def summary(store=Depends(get_execution_store)):
    records = store.list_all()
    status_counts = Counter(str(record.get("status", "unknown")) for record in records)
    return ApiResponse.ok({
        "total_executions": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "latest_execution_at": records[0].get("created_at") if records else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/events")
def events(
    limit: int = Query(default=100, ge=1, le=500),
    execution_id: str | None = Query(default=None),
    store=Depends(get_execution_store),
):
    """Normalize stored execution and node lifecycle state into event records."""
    records = store.list_all()
    output: list[dict[str, object]] = []
    for record in records:
        if execution_id and record.get("execution_id") != execution_id:
            continue
        identifier = str(record.get("execution_id", "unknown"))
        output.append({
            "event_type": "execution",
            "execution_id": identifier,
            "node_id": None,
            "status": record.get("status", "unknown"),
            "timestamp": record.get("completed_at") or record.get("started_at") or record.get("created_at"),
            "message": record.get("message", ""),
        })
        for node in record.get("nodes", []):
            output.append({
                "event_type": "node",
                "execution_id": identifier,
                "node_id": node.get("node_id"),
                "status": node.get("status", "unknown"),
                "timestamp": node.get("finished_at") or node.get("started_at"),
                "message": node.get("error_message") or "",
            })
    output.sort(key=lambda event: str(event.get("timestamp") or ""), reverse=True)
    return ApiResponse.ok(output[:limit], execution_id=execution_id)
