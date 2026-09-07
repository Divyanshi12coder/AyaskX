"""api/routers/recovery.py — Fault detection and self-healing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_execution_store, get_orchestrator
from api.schemas.common import ApiResponse
from api.services.recovery_service import RecoveryService

router = APIRouter(prefix="/v1/pipelines", tags=["Recovery"])


def _svc(
    store=Depends(get_execution_store),
    orchestrator=Depends(get_orchestrator),
) -> RecoveryService:
    return RecoveryService(execution_store=store, orchestrator=orchestrator)


def _require_execution(execution_id: str, store=Depends(get_execution_store)):
    if not store.exists(execution_id):
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")


class HealRequest(BaseModel):
    auto_approve_low_risk: bool = False


@router.get("/{execution_id}/fault")
def get_fault(execution_id: str, svc: RecoveryService = Depends(_svc)):
    _require_execution(execution_id, svc._store)
    return ApiResponse.ok(svc.get_fault(execution_id), execution_id=execution_id)


@router.get("/{execution_id}/fault/localization")
def get_localization(execution_id: str, svc: RecoveryService = Depends(_svc)):
    _require_execution(execution_id, svc._store)
    return ApiResponse.ok(svc.get_localization(execution_id), execution_id=execution_id)


@router.get("/{execution_id}/fault/root-cause")
def get_root_cause(execution_id: str, svc: RecoveryService = Depends(_svc)):
    _require_execution(execution_id, svc._store)
    return ApiResponse.ok(svc.get_root_cause(execution_id), execution_id=execution_id)


@router.get("/{execution_id}/recovery/decision")
def get_decision(execution_id: str, svc: RecoveryService = Depends(_svc)):
    _require_execution(execution_id, svc._store)
    return ApiResponse.ok(svc.get_recovery_decision(execution_id), execution_id=execution_id)


@router.get("/{execution_id}/recovery/plan")
def get_plan(execution_id: str, svc: RecoveryService = Depends(_svc)):
    _require_execution(execution_id, svc._store)
    return ApiResponse.ok(svc.get_repair_plan(execution_id), execution_id=execution_id)


@router.get("/{execution_id}/recovery/result")
def get_result(execution_id: str, svc: RecoveryService = Depends(_svc)):
    _require_execution(execution_id, svc._store)
    return ApiResponse.ok(svc.get_recovery_result(execution_id), execution_id=execution_id)


@router.get("/{execution_id}/self-healing")
def get_self_healing(execution_id: str, svc: RecoveryService = Depends(_svc)):
    _require_execution(execution_id, svc._store)
    return ApiResponse.ok(svc.get_self_healing(execution_id), execution_id=execution_id)


@router.post("/{execution_id}/self-healing/trigger", status_code=202)
def trigger_self_healing(
    execution_id: str,
    body: HealRequest,
    svc: RecoveryService = Depends(_svc),
):
    _require_execution(execution_id, svc._store)
    result = svc.trigger_self_healing(
        execution_id,
        auto_approve_low_risk=body.auto_approve_low_risk,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return ApiResponse.ok(result, execution_id=execution_id)
