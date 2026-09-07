"""api/routers/models.py — Model endpoints (candidates, best model, metrics)."""

from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_execution_store
from api.schemas.common import ApiResponse

router = APIRouter(prefix="/v1/pipelines", tags=["Models"])


def _exec(execution_id: str, store=Depends(get_execution_store)):
    rec = store.get(execution_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return rec


@router.get("/{execution_id}/candidates")
def get_candidates(rec=Depends(_exec)):
    return ApiResponse.ok(
        rec.get("candidates", []),
        execution_id=rec["execution_id"],
    )


@router.get("/{execution_id}/model")
def get_model(rec=Depends(_exec)):
    return ApiResponse.ok(
        {
            "best_model": rec.get("best_model"),
            "best_score": rec.get("best_score"),
            "training_result": rec.get("training_result"),
        },
        execution_id=rec["execution_id"],
    )


@router.get("/{execution_id}/model/metrics")
def get_metrics(rec=Depends(_exec)):
    tr = rec.get("training_result") or {}
    metrics = tr.get("evaluations") if isinstance(tr, dict) else None
    return ApiResponse.ok(
        {"metrics": metrics, "best_score": rec.get("best_score")},
        execution_id=rec["execution_id"],
    )


@router.get("/{execution_id}/model/validation-strategy")
def get_validation_strategy(rec=Depends(_exec)):
    return ApiResponse.ok(
        {
            "validation_strategy": rec.get("validation_strategy"),
            "detail": rec.get("validation_strategy_detail"),
        },
        execution_id=rec["execution_id"],
    )
