from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from .status import NodeStatus, PipelineStatus
from .checkpoints import CheckpointManager


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NodeExecution:
    execution_id: str
    node_id: str
    status: NodeStatus

    started_at: datetime
    finished_at: datetime | None = None

    input_metadata: dict[str, Any] = field(
        default_factory=dict
    )

    output_metadata: dict[str, Any] = field(
        default_factory=dict
    )

    error_type: str | None = None
    error_message: str | None = None

    checkpoint_id: str | None = None


    @property
    def duration_seconds(self) -> float | None:

        if self.finished_at is None:
            return None

        return (
            self.finished_at
            - self.started_at
        ).total_seconds()


@dataclass(frozen=True)
class PipelineExecution:

    execution_id: str
    status: PipelineStatus

    nodes: tuple[
        NodeExecution,
        ...
    ]

    started_at: datetime
    finished_at: datetime | None = None


    @property
    def failed_node(
        self,
    ) -> NodeExecution | None:

        for node in self.nodes:

            if node.status == NodeStatus.FAILED:
                return node

        return None


    @property
    def last_successful_node(
        self,
    ) -> NodeExecution | None:

        for node in reversed(self.nodes):

            if node.status == NodeStatus.SUCCESS:
                return node

        return None


class PipelineExecutor:
    """
    Core sequential pipeline execution engine.

    Responsibilities
    ----------------
    - Create execution IDs
    - Execute nodes deterministically
    - Track node lifecycle
    - Record failures
    - Create checkpoints after successful nodes
    - Preserve execution history
    - Identify the first failed node
    - Expose the last known good checkpoint

    Deliberately NOT responsible for:
    - automatic repair
    - arbitrary retries
    - LLM-generated code execution
    - production modification
    - security incident response

    Those belong to future recovery layers.
    """


    def __init__(
        self,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> None:

        self.checkpoint_manager = (
            checkpoint_manager
            or CheckpointManager()
        )

        self._history: list[
            PipelineExecution
        ] = []


    # =========================================================
    # EXECUTE
    # =========================================================

    def execute(
        self,
        nodes: Iterable[Any],
        *,
        context: Any = None,
    ) -> PipelineExecution:

        execution_id = str(uuid4())

        pipeline_started_at = _utc_now()

        executions: list[
            NodeExecution
        ] = []


        for node in nodes:

            node_id = self._node_id(node)

            node_execution_id = str(
                uuid4()
            )

            node_started_at = _utc_now()


            input_metadata = (
                self._input_metadata(
                    node,
                    context,
                )
            )


            try:

                result = self._run_node(
                    node,
                    context,
                )


                output_metadata = (
                    self._output_metadata(
                        result
                    )
                )


                # -------------------------------------------------
                # VALIDATE NODE OUTPUT
                # -------------------------------------------------

                self._validate_node_output(
                    node,
                    result,
                )


                # -------------------------------------------------
                # CREATE CHECKPOINT
                # -------------------------------------------------

                checkpoint = (
                    self._create_checkpoint(
                        node=node,
                        execution_id=execution_id,
                        result=result,
                        input_metadata=input_metadata,
                        output_metadata=output_metadata,
                    )
                )


                node_execution = NodeExecution(

                    execution_id=node_execution_id,

                    node_id=node_id,

                    status=NodeStatus.SUCCESS,

                    started_at=node_started_at,

                    finished_at=_utc_now(),

                    input_metadata=input_metadata,

                    output_metadata=output_metadata,

                    checkpoint_id=(
                        checkpoint.checkpoint_id
                        if checkpoint
                        else None
                    ),
                )


                executions.append(
                    node_execution
                )


                # -------------------------------------------------
                # PROPAGATE RESULT
                # -------------------------------------------------

                context = self._update_context(
                    context,
                    result,
                )


            except Exception as exc:

                node_execution = NodeExecution(

                    execution_id=node_execution_id,

                    node_id=node_id,

                    status=NodeStatus.FAILED,

                    started_at=node_started_at,

                    finished_at=_utc_now(),

                    input_metadata=input_metadata,

                    error_type=type(exc).__name__,

                    error_message=str(exc),
                )


                executions.append(
                    node_execution
                )


                # -------------------------------------------------
                # STOP IMMEDIATELY
                # -------------------------------------------------
                #
                # Never continue after an unresolved
                # pipeline failure.
                #

                execution = PipelineExecution(

                    execution_id=execution_id,

                    status=PipelineStatus.FAILED,

                    nodes=tuple(executions),

                    started_at=pipeline_started_at,

                    finished_at=_utc_now(),
                )


                self._history.append(
                    execution
                )

                return execution


        execution = PipelineExecution(

            execution_id=execution_id,

            status=PipelineStatus.SUCCESS,

            nodes=tuple(executions),

            started_at=pipeline_started_at,

            finished_at=_utc_now(),
        )


        self._history.append(
            execution
        )

        return execution


    # =========================================================
    # CHECKPOINT
    # =========================================================

    def _create_checkpoint(
        self,
        *,
        node: Any,
        execution_id: str,
        result: Any,
        input_metadata: dict[str, Any],
        output_metadata: dict[str, Any],
    ):

        manager = self.checkpoint_manager

        node_version = getattr(
            node,
            "version",
            "unknown",
        )


        input_schema = self._schema_from_metadata(
            input_metadata
        )

        output_schema = self._schema_from_metadata(
            output_metadata
        )


        return manager.create(

            execution_id=execution_id,

            node_id=self._node_id(node),

            artifact=result,

            node_version=str(
                node_version
            ),

            input_schema=input_schema,

            output_schema=output_schema,

            validation_status="passed",

            metadata={
                "node_type": type(node).__name__,
            },
        )


    # =========================================================
    # NODE OUTPUT VALIDATION
    # =========================================================

    @staticmethod
    def _validate_node_output(
        node: Any,
        result: Any,
    ) -> None:

        validator = getattr(
            node,
            "validate_output",
            None,
        )

        if callable(validator):

            valid = validator(result)

            if valid is False:

                raise ValueError(
                    "Node output validation failed."
                )


    # =========================================================
    # NODE IDENTIFICATION
    # =========================================================

    @staticmethod
    def _node_id(
        node: Any,
    ) -> str:

        node_id = getattr(
            node,
            "node_id",
            None,
        )

        if node_id:
            return str(node_id)


        if callable(node):

            name = getattr(
                node,
                "__name__",
                None,
            )

            if name:
                return str(name)


        return node.__class__.__name__


    # =========================================================
    # NODE EXECUTION
    # =========================================================

    @staticmethod
    def _run_node(
        node: Any,
        context: Any,
    ) -> Any:

        run = getattr(
            node,
            "run",
            None,
        )

        if callable(run):

            return run(context)


        if callable(node):

            return node(context)


        raise TypeError(
            f"Pipeline node '{node}' must provide "
            "run(context) or be callable."
        )


    # =========================================================
    # INPUT METADATA
    # =========================================================

    @staticmethod
    def _input_metadata(
        node: Any,
        context: Any,
    ) -> dict[str, Any]:

        provider = getattr(
            node,
            "input_metadata",
            None,
        )

        if callable(provider):

            metadata = provider(context)

            if isinstance(
                metadata,
                dict,
            ):

                return dict(metadata)


        return {}


    # =========================================================
    # OUTPUT METADATA
    # =========================================================

    @staticmethod
    def _output_metadata(
        result: Any,
    ) -> dict[str, Any]:

        if result is None:
            return {}


        metadata = {
            "result_type": type(
                result
            ).__name__,
        }


        shape = getattr(
            result,
            "shape",
            None,
        )

        if shape is not None:

            try:

                metadata["shape"] = tuple(
                    shape
                )

            except TypeError:
                pass


        columns = getattr(
            result,
            "columns",
            None,
        )

        if columns is not None:

            try:

                metadata["columns"] = [
                    str(column)
                    for column in columns
                ]

            except TypeError:
                pass


        return metadata


    # =========================================================
    # SCHEMA METADATA
    # =========================================================

    @staticmethod
    def _schema_from_metadata(
        metadata: dict[str, Any],
    ) -> dict[str, Any]:

        schema = {}

        if "shape" in metadata:
            schema["shape"] = metadata[
                "shape"
            ]

        if "columns" in metadata:
            schema["columns"] = metadata[
                "columns"
            ]

        if "result_type" in metadata:
            schema["result_type"] = metadata[
                "result_type"
            ]

        return schema

        # =========================================================
    # CONTEXT PROPAGATION
    # =========================================================

    @staticmethod
    def _update_context(
        context: Any,
        result: Any,
    ) -> Any:

        if context is None:
            return result

        # Node may mutate and return the same context object.
        # Never assign context.value = context in that case.
        if result is context:
            return context

        setter = getattr(
            context,
            "set_value",
            None,
        )

        if callable(setter):
            setter(result)
            return context

        if hasattr(
            context,
            "value",
        ):
            try:
                context.value = result
                return context
            except Exception:
                pass

        return result

    



    

        # =========================================================
    # RECOVERY INFORMATION
    # =========================================================

    def last_known_good_checkpoint(
        self,
        execution: Any,
    ):
        """
        Return the latest valid checkpoint associated with
        the supplied pipeline execution.

        Accepts either:
        - PipelineExecution
        - execution_id string

        Returns None when no successful checkpoint exists.
        """

        execution_id = getattr(
            execution,
            "execution_id",
            execution,
        )

        return (
            self.checkpoint_manager.last_known_good(
                execution_id=str(execution_id)
            )
        )      
    # =========================================================
    # HISTORY
    # =========================================================

    def history(
        self,
    ) -> tuple[PipelineExecution, ...]:
        """
        Return immutable execution history.

        Existing executions are never modified.
        """

        return tuple(self._history)


        
    


    # =========================================================
    # FAULT ANALYSIS  (additive — does NOT change existing API)
    # =========================================================

    def analyze_failure(
        self,
        execution: "PipelineExecution",
        events: tuple = (),
    ) -> "tuple[Any, Any, Any]":
        """
        Convenience method: run the full fault analysis pipeline.

        Returns
        -------
        (FaultReport, FaultLocalization, RecoveryDecision)

        This method is PURELY ANALYTICAL.
        It does NOT execute recovery, modify pipeline state, or retry.

        The last-known-good checkpoint for this execution is looked up
        automatically from the CheckpointManager.

        Parameters
        ----------
        execution : PipelineExecution
            A completed (SUCCESS or FAILED) pipeline execution.
        events : tuple of NodeEvent, optional
            Structured observability events for richer localization.
        """

        from core.fault.detector import FaultDetector
        from core.fault.localizer import FaultLocalizer
        from core.recovery.decision import RecoveryDecisionEngine

        detector = FaultDetector()
        localizer = FaultLocalizer()
        decision_engine = RecoveryDecisionEngine()

        fault = detector.detect(execution)

        localization = localizer.localize(
            execution,
            fault,
            events=events,
        )

        last_checkpoint = self.last_known_good_checkpoint(
            execution.execution_id
        )

        decision = decision_engine.decide(
            execution,
            fault,
            localization,
            last_known_good_checkpoint=last_checkpoint,
        )

        return fault, localization, decision