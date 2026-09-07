from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class NodeEvent:
    execution_id: str
    pipeline_id: str
    node_id: str

    event_type: str

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    status: str | None = None

    message: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )