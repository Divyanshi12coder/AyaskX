from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PipelineContext:
    """
    Runtime context shared between AyaskX pipeline nodes.

    The context intentionally stores metadata separately from
    actual artifacts so future checkpointing/object storage can
    be introduced without changing node interfaces.
    """

    execution_id: str
    pipeline_id: str

    artifacts: dict[str, Any] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    node_outputs: dict[str, Any] = field(
        default_factory=dict
    )

    node_status: dict[str, str] = field(
        default_factory=dict
    )

    started_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    finished_at: datetime | None = None

    def set_artifact(
        self,
        name: str,
        artifact: Any,
    ) -> None:
        self.artifacts[name] = artifact

    def get_artifact(
        self,
        name: str,
    ) -> Any:

        if name not in self.artifacts:
            raise KeyError(
                f"Artifact not found: {name}"
            )

        return self.artifacts[name]

    def set_node_output(
        self,
        node_id: str,
        output: Any,
    ) -> None:

        self.node_outputs[node_id] = output

    def set_node_status(
        self,
        node_id: str,
        status: str,
    ) -> None:

        self.node_status[node_id] = status

    def finish(self) -> None:
        self.finished_at = datetime.now(
            timezone.utc
        )