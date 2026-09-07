"""api/exceptions.py — AyaskX API exception handlers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("ayaskx.api")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotFoundError(Exception):
    def __init__(self, resource: str, resource_id: str) -> None:
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} '{resource_id}' not found")


class ValidationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class UploadTooLargeError(Exception):
    def __init__(self, max_mb: int) -> None:
        super().__init__(f"Upload exceeds maximum size of {max_mb} MB")


class UnsupportedFileTypeError(Exception):
    def __init__(self, filename: str) -> None:
        super().__init__(f"Unsupported file type: {filename}")


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "status": "error",
            "data": None,
            "errors": [str(exc)],
            "timestamp": _now(),
        },
    )


async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "data": None,
            "errors": [str(exc)],
            "timestamp": _now(),
        },
    )


async def upload_too_large_handler(request: Request, exc: UploadTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content={
            "status": "error",
            "data": None,
            "errors": [str(exc)],
            "timestamp": _now(),
        },
    )


async def unsupported_file_handler(request: Request, exc: UnsupportedFileTypeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content={
            "status": "error",
            "data": None,
            "errors": [str(exc)],
            "timestamp": _now(),
        },
    )


async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception in API: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "data": None,
            "errors": ["Internal server error. Check server logs."],
            "timestamp": _now(),
        },
    )
