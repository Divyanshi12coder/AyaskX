"""api/routers/pipelines.py — Pipeline execution endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from api.dependencies import get_execution_store, get_dataset_store, get_orchestrator
from api.schemas.common import ApiResponse
from api.services.pipeline_service import PipelineService

router = APIRouter(prefix="/v1/pipelines", tags=["Pipelines"])


class RunRequest(BaseModel):
    dataset_id: str
    target: str | None = None
    task_type: str | None = None
    max_candidates: int | None = None


def _svc(
    execution_store=Depends(get_execution_store),
    orchestrator=Depends(get_orchestrator),
) -> PipelineService:
    return PipelineService(orchestrator=orchestrator, execution_store=execution_store)


# POST /v1/pipelines/run
@router.post("/run", status_code=202)
def run_pipeline(
    body: RunRequest,
    svc: PipelineService = Depends(_svc),
    dataset_store=Depends(get_dataset_store),
):
    rec = dataset_store.get(body.dataset_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Dataset '{body.dataset_id}' not found")

    import pandas as pd
    from pathlib import Path
    try:
        path = Path(rec["file_path"])
        ext = Path(rec["safe_filename"]).suffix.lower()
        df = pd.read_csv(path) if ext in (".csv", ".tsv") else pd.read_parquet(path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot load dataset: {exc}")

    execution_id = svc.start_run(
        df,
        dataset_id=body.dataset_id,
        dataset_path=rec["original_filename"],
        target=body.target,
        task_type=body.task_type,
        max_candidates=body.max_candidates,
    )
    return ApiResponse.ok(
        {"execution_id": execution_id, "status": "queued"},
        execution_id=execution_id,
    )


# GET /v1/pipelines (list)
@router.get("")
def list_pipelines(svc: PipelineService = Depends(_svc)):
    return ApiResponse.ok(svc.list_executions())


# GET /v1/pipelines/{execution_id}
@router.get("/{execution_id}")
def get_pipeline(execution_id: str, svc: PipelineService = Depends(_svc)):
    rec = svc.get_execution(execution_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ApiResponse.ok(rec, execution_id=execution_id)


# GET /v1/pipelines/{execution_id}/status
@router.get("/{execution_id}/status")
def get_status(execution_id: str, svc: PipelineService = Depends(_svc)):
    status = svc.get_status(execution_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ApiResponse.ok({"status": status}, execution_id=execution_id)


# GET /v1/pipelines/{execution_id}/nodes
@router.get("/{execution_id}/nodes")
def get_nodes(execution_id: str, svc: PipelineService = Depends(_svc)):
    if not svc.get_execution(execution_id):
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ApiResponse.ok(svc.get_nodes(execution_id), execution_id=execution_id)


# GET /v1/pipelines/{execution_id}/nodes/{node_id}
@router.get("/{execution_id}/nodes/{node_id}")
def get_node(execution_id: str, node_id: str, svc: PipelineService = Depends(_svc)):
    node = svc.get_node(execution_id, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in execution '{execution_id}'")
    return ApiResponse.ok(node, execution_id=execution_id)


# GET /v1/pipelines/{execution_id}/checkpoints
@router.get("/{execution_id}/checkpoints")
def get_checkpoints(execution_id: str, svc: PipelineService = Depends(_svc)):
    if not svc.get_execution(execution_id):
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ApiResponse.ok(svc.get_checkpoints(execution_id), execution_id=execution_id)


# GET /v1/pipelines/{execution_id}/checkpoints/{checkpoint_id}
@router.get("/{execution_id}/checkpoints/{checkpoint_id}")
def get_checkpoint(execution_id: str, checkpoint_id: str, svc: PipelineService = Depends(_svc)):
    ckpt = svc.get_checkpoint(execution_id, checkpoint_id)
    if ckpt is None:
        raise HTTPException(status_code=404, detail=f"Checkpoint '{checkpoint_id}' not found")
    return ApiResponse.ok(ckpt, execution_id=execution_id)
