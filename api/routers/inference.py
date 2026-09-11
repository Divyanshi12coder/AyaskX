"""api/routers/inference.py — POST /v1/pipelines/{execution_id}/predict."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_execution_store, get_orchestrator
from api.schemas.common import ApiResponse

router = APIRouter(prefix="/v1/pipelines", tags=["Inference"])


class PredictRequest(BaseModel):
    rows: list[dict[str, Any]]


@router.post("/{execution_id}/predict")
def predict(
    execution_id: str,
    body: PredictRequest,
    store=Depends(get_execution_store),
    orchestrator=Depends(get_orchestrator),
):
    rec = store.get(execution_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    if rec.get("status") not in ("succeeded",):
        raise HTTPException(
            status_code=422,
            detail=f"Execution '{execution_id}' has status '{rec.get('status')}'. Inference requires 'succeeded'.",
        )

    import pandas as pd
    try:
        df = pd.DataFrame(body.rows)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid input rows: {exc}")

    try:
        import uuid
        from core.inference.engine import InferenceRequest
        request = InferenceRequest(
            request_id=str(uuid.uuid4()),
            execution_id=execution_id,
            data=df,
        )
        # Load the artifact that was saved during the pipeline run
        artifact_root = orchestrator._artifact_root
        artifact_files = list(artifact_root.glob(f"{execution_id}*.joblib"))
        if not artifact_files:
            raise HTTPException(
                status_code=404,
                detail=f"No model artifact found for execution '{execution_id}'",
            )
        from core.inference.engine import InferenceEngine, ModelArtifact
        engine = InferenceEngine()
        artifact = ModelArtifact.load(artifact_files[0])
        result = engine.predict(artifact, request)
        if not result.success:
            raise HTTPException(status_code=422, detail=result.message)
        predictions = result.predictions.tolist() if hasattr(result.predictions, "tolist") else list(result.predictions)
        return ApiResponse.ok(
            {
                "predictions": predictions,
                "request_id": result.request_id,
                "model_name": result.model_name,
                "n_samples": result.input_rows,
            },
            execution_id=execution_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inference failed: {exc}")
