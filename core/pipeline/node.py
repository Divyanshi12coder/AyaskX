from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.pipeline.context import PipelineContext
from core.pipeline.status import NodeStatus


@dataclass(frozen=True)
class NodeResult:
    node_id: str
    status: NodeStatus
    output: Any = None

    error_type: str | None = None
    error_message: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


class PipelineNode(ABC):
    """
    Base contract for every AyaskX pipeline stage.

    Future fault localization depends on every stage exposing
    the same execution/validation/checkpoint lifecycle.
    """

    def __init__(
        self,
        node_id: str,
        version: str = "1.0.0",
    ):

        if not node_id:
            raise ValueError(
                "node_id cannot be empty."
            )

        self.node_id = node_id
        self.version = version

    # ----------------------------------------------------------
    # Execution
    # ----------------------------------------------------------

    def execute(
        self,
        context: PipelineContext,
    ) -> NodeResult:

        context.set_node_status(
            self.node_id,
            NodeStatus.RUNNING.value,
        )

        try:

            self.validate_input(context)

            output = self.run(context)

            self.validate_output(
                output,
                context,
            )

            context.set_node_output(
                self.node_id,
                output,
            )

            context.set_node_status(
                self.node_id,
                NodeStatus.SUCCESS.value,
            )

            return NodeResult(
                node_id=self.node_id,
                status=NodeStatus.SUCCESS,
                output=output,
                metadata={
                    "node_version": self.version,
                },
            )

        except Exception as exc:

            context.set_node_status(
                self.node_id,
                NodeStatus.FAILED.value,
            )

            return NodeResult(
                node_id=self.node_id,
                status=NodeStatus.FAILED,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata={
                    "node_version": self.version,
                },
            )

    # ----------------------------------------------------------
    # Node implementation
    # ----------------------------------------------------------

    @abstractmethod
    def run(
        self,
        context: PipelineContext,
    ) -> Any:
        """
        Execute node logic.
        """
        raise NotImplementedError

    # ----------------------------------------------------------
    # Validation hooks
    # ----------------------------------------------------------

    def validate_input(
        self,
        context: PipelineContext,
    ) -> None:
        """
        Validate dependencies/input artifacts before execution.
        """
        return None

    def validate_output(
        self,
        output: Any,
        context: PipelineContext,
    ) -> None:
        """
        Validate node output before accepting it.
        """
        return None

    # ----------------------------------------------------------
    # Recovery hooks
    # ----------------------------------------------------------

    def checkpoint_metadata(
        self,
        context: PipelineContext,
    ) -> dict[str, Any]:

        return {
            "node_id": self.node_id,
            "node_version": self.version,
            "execution_id": context.execution_id,
            "pipeline_id": context.pipeline_id,
        }

    def health_check(
        self,
        context: PipelineContext,
    ) -> bool:

        return True