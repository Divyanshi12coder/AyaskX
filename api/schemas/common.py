"""api/schemas/common.py — Shared response envelope and base schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiResponse(BaseModel):
    """Standard response envelope for all AyaskX API responses."""

    status: str = "success"
    execution_id: str | None = None
    data: Any = None
    errors: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utc_now)

    @classmethod
    def ok(
        cls,
        data: Any,
        *,
        execution_id: str | None = None,
    ) -> "ApiResponse":
        return cls(status="success", data=data, execution_id=execution_id)

    @classmethod
    def error(
        cls,
        errors: list[str],
        *,
        execution_id: str | None = None,
    ) -> "ApiResponse":
        return cls(
            status="error",
            data=None,
            errors=errors,
            execution_id=execution_id,
        )

    model_config = {"populate_by_name": True}
