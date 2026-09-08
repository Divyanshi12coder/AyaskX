from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from core.database import (
    FaultEvent,
    PipelineExecution,
    RecoveryEvent,
    get_session,
)


class ExecutionRepository:

    def create_execution(
        self,
        execution_id: str,
        dataset_path: str | None = None,
        dataset_fingerprint: str | None = None,
        status: str = "started",
    ) -> PipelineExecution:

        with get_session() as session:
            execution = PipelineExecution(
                execution_id=execution_id,
                dataset_path=dataset_path,
                dataset_fingerprint=dataset_fingerprint,
                status=status,
                success=False,
            )

            session.add(execution)
            session.commit()
            session.refresh(execution)

            return execution

    def complete_execution(
        self,
        execution_id: str,
        success: bool,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> PipelineExecution | None:

        with get_session() as session:
            execution = session.scalar(
                select(PipelineExecution).where(
                    PipelineExecution.execution_id
                    == execution_id
                )
            )

            if execution is None:
                return None

            execution.success = success
            execution.status = (
                status
                if status is not None
                else ("completed" if success else "failed")
            )
            execution.message = message
            execution.result = result
            execution.completed_at = datetime.now(timezone.utc)

            session.commit()
            session.refresh(execution)

            return execution

    def get_execution(
        self,
        execution_id: str,
    ) -> PipelineExecution | None:

        with get_session() as session:
            return session.scalar(
                select(PipelineExecution).where(
                    PipelineExecution.execution_id
                    == execution_id
                )
            )

    def list_executions(
        self,
        limit: int = 100,
    ) -> list[PipelineExecution]:

        if limit <= 0:
            raise ValueError("limit must be positive.")

        with get_session() as session:
            return list(
                session.scalars(
                    select(PipelineExecution)
                    .order_by(
                        PipelineExecution.created_at.desc()
                    )
                    .limit(limit)
                )
            )

    def record_fault(
        self,
        execution_id: str,
        fault_type: str,
        severity: str = "unknown",
        component: str | None = None,
        message: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> FaultEvent:

        with get_session() as session:
            fault = FaultEvent(
                execution_id=execution_id,
                fault_type=fault_type,
                severity=severity,
                component=component,
                message=message,
                evidence=evidence,
            )

            session.add(fault)
            session.commit()
            session.refresh(fault)

            return fault

    def get_faults(
        self,
        execution_id: str,
    ) -> list[FaultEvent]:

        with get_session() as session:
            return list(
                session.scalars(
                    select(FaultEvent)
                    .where(
                        FaultEvent.execution_id
                        == execution_id
                    )
                    .order_by(FaultEvent.created_at.asc())
                )
            )

    def record_recovery(
        self,
        execution_id: str,
        decision: str,
        status: str,
        action: str | None = None,
        reason: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> RecoveryEvent:

        with get_session() as session:
            recovery = RecoveryEvent(
                execution_id=execution_id,
                decision=decision,
                action=action,
                status=status,
                reason=reason,
                evidence=evidence,
            )

            session.add(recovery)
            session.commit()
            session.refresh(recovery)

            return recovery

    def get_recoveries(
        self,
        execution_id: str,
    ) -> list[RecoveryEvent]:

        with get_session() as session:
            return list(
                session.scalars(
                    select(RecoveryEvent)
                    .where(
                        RecoveryEvent.execution_id
                        == execution_id
                    )
                    .order_by(RecoveryEvent.created_at.asc())
                )
            )