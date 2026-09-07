"""api/routers/datasets.py — Dataset endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status

from api.config import Settings, get_settings
from api.dependencies import get_dataset_store
from api.exceptions import NotFoundError, UploadTooLargeError, UnsupportedFileTypeError
from api.repositories.dataset_store import DatasetStore
from api.schemas.common import ApiResponse
from api.services.dataset_service import DatasetService

router = APIRouter(prefix="/v1/datasets", tags=["Datasets"])


def _svc(
    settings: Annotated[Settings, Depends(get_settings)],
    ds: Annotated[DatasetStore, Depends(get_dataset_store)],
) -> DatasetService:
    return DatasetService(
        dataset_store=ds,
        upload_tmp_root=settings.upload_tmp_root,
        max_upload_bytes=settings.max_upload_bytes,
    )


# POST /v1/datasets/upload
@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    svc: DatasetService = Depends(_svc),
):
    content = await file.read()
    try:
        record = svc.upload(file.filename or "upload.csv", content)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    return ApiResponse.ok(record)


# GET /v1/datasets (list all)
@router.get("")
def list_datasets(svc: DatasetService = Depends(_svc)):
    return ApiResponse.ok(svc.list_datasets())


# GET /v1/datasets/{dataset_id}
@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, svc: DatasetService = Depends(_svc)):
    rec = svc.get_metadata(dataset_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    return ApiResponse.ok(rec)


# GET /v1/datasets/{dataset_id}/profile
@router.get("/{dataset_id}/profile")
def get_profile(dataset_id: str, svc: DatasetService = Depends(_svc)):
    if not svc.get_metadata(dataset_id):
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    return ApiResponse.ok(svc.get_profile(dataset_id))


# GET /v1/datasets/{dataset_id}/feature-roles
@router.get("/{dataset_id}/feature-roles")
def get_feature_roles(dataset_id: str, svc: DatasetService = Depends(_svc)):
    if not svc.get_metadata(dataset_id):
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    return ApiResponse.ok(svc.get_feature_roles(dataset_id))


# GET /v1/datasets/{dataset_id}/leakage
@router.get("/{dataset_id}/leakage")
def get_leakage(dataset_id: str, svc: DatasetService = Depends(_svc)):
    if not svc.get_metadata(dataset_id):
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    return ApiResponse.ok(svc.get_leakage(dataset_id))
