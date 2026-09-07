from core.checkpoints import CheckpointManager
from core.observability import PipelineLogger
from core.pipeline import (
    PipelineContext,
    PipelineNode,
    NodeStatus,
)


class SuccessfulNode(PipelineNode):

    def run(self, context):

        return {
            "value": 42
        }


class FailingNode(PipelineNode):

    def run(self, context):

        raise RuntimeError(
            "intentional failure"
        )


def test_successful_node_execution():

    context = PipelineContext(
        execution_id="exec-001",
        pipeline_id="pipeline-001",
    )

    node = SuccessfulNode(
        node_id="test_node"
    )

    result = node.execute(context)

    assert result.status == NodeStatus.SUCCESS
    assert result.output["value"] == 42

    assert (
        context.node_status["test_node"]
        == "success"
    )


def test_failed_node_execution_is_observable():

    context = PipelineContext(
        execution_id="exec-002",
        pipeline_id="pipeline-001",
    )

    node = FailingNode(
        node_id="failing_node"
    )

    result = node.execute(context)

    assert result.status == NodeStatus.FAILED
    assert result.error_type == "RuntimeError"

    assert (
        context.node_status["failing_node"]
        == "failed"
    )


def test_checkpoint_creation():

    context = PipelineContext(
        execution_id="exec-003",
        pipeline_id="pipeline-001",
    )

    node = SuccessfulNode(
        node_id="checkpoint_node"
    )

    result = node.execute(context)

    manager = CheckpointManager()

    checkpoint = manager.create(
        node=node,
        context=context,
        artifact=result.output,
    )

    assert checkpoint.node_id == (
        "checkpoint_node"
    )

    assert checkpoint.execution_id == (
        "exec-003"
    )

    assert checkpoint.validation_status == (
        "passed"
    )

    restored = manager.get_artifact(
        checkpoint.checkpoint_id
    )

    assert restored == {
        "value": 42
    }


def test_last_known_good_checkpoint():

    context = PipelineContext(
        execution_id="exec-004",
        pipeline_id="pipeline-001",
    )

    node = SuccessfulNode(
        node_id="good_node"
    )

    result = node.execute(context)

    manager = CheckpointManager()

    checkpoint = manager.create(
        node=node,
        context=context,
        artifact=result.output,
    )

    recovered = manager.last_known_good(
        "exec-004"
    )

    assert recovered is not None
    assert (
        recovered.checkpoint_id
        == checkpoint.checkpoint_id
    )


def test_pipeline_logger_records_events():

    logger = PipelineLogger()

    logger.node_started(
        execution_id="exec-005",
        pipeline_id="pipeline-001",
        node_id="node_a",
    )

    logger.node_completed(
        execution_id="exec-005",
        pipeline_id="pipeline-001",
        node_id="node_a",
    )

    assert len(logger.events) == 2

    assert (
        logger.events[0].event_type
        == "node_started"
    )

    assert (
        logger.events[1].event_type
        == "node_completed"
    )