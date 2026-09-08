from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.database.connection import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineExecution(Base):
    __tablename__ = "pipeline_executions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    execution_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    dataset_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    dataset_fingerprint: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="started",
    )

    success: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class FaultEvent(Base):
    __tablename__ = "fault_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    execution_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    fault_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
    )

    component: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class RecoveryEvent(Base):
    __tablename__ = "recovery_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    execution_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    decision: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    action: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )