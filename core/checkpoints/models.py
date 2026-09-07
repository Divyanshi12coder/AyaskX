from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str

    execution_id: str
    pipeline_id: str
    node_id: str

    node_version: str

    created_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    artifact_reference: str | None = None

    input_schema: dict[str, Any] = field(
        default_factory=dict
    )

    output_schema: dict[str, Any] = field(
        default_factory=dict
    )

    data_hash: str | None = None

    configuration: dict[str, Any] = field(
        default_factory=dict
    )

    dependency_versions: dict[str, str] = field(
        default_factory=dict
    )

    validation_status: str = "unknown"

    metadata: dict[str, Any] = field(
        default_factory=dict
    )