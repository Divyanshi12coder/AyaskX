import logging
from typing import Any

from core.observability.events import NodeEvent


class PipelineLogger:
    """
    Structured pipeline event logger.

    Events are kept in memory for now.

    Later the same events can be persisted to:
        PostgreSQL
        OpenTelemetry
        Elasticsearch/OpenSearch
        object storage
    """

    def __init__(
        self,
        logger_name: str = "ayaskx.pipeline",
    ):

        self.logger = logging.getLogger(
            logger_name
        )

        self.events: list[
            NodeEvent
        ] = []

    def emit(
        self,
        event: NodeEvent,
    ) -> None:

        self.events.append(event)

        self.logger.info(
            "%s | execution=%s | pipeline=%s | node=%s | status=%s | %s",
            event.event_type,
            event.execution_id,
            event.pipeline_id,
            event.node_id,
            event.status,
            event.message or "",
        )

    def node_started(
        self,
        execution_id: str,
        pipeline_id: str,
        node_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:

        self.emit(
            NodeEvent(
                execution_id=execution_id,
                pipeline_id=pipeline_id,
                node_id=node_id,
                event_type="node_started",
                status="running",
                metadata=metadata or {},
            )
        )

    def node_completed(
        self,
        execution_id: str,
        pipeline_id: str,
        node_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:

        self.emit(
            NodeEvent(
                execution_id=execution_id,
                pipeline_id=pipeline_id,
                node_id=node_id,
                event_type="node_completed",
                status="success",
                metadata=metadata or {},
            )
        )

    def node_failed(
        self,
        execution_id: str,
        pipeline_id: str,
        node_id: str,
        error: Exception,
    ) -> None:

        self.emit(
            NodeEvent(
                execution_id=execution_id,
                pipeline_id=pipeline_id,
                node_id=node_id,
                event_type="node_failed",
                status="failed",
                message=str(error),
                metadata={
                    "error_type": type(error).__name__,
                },
            )
        )