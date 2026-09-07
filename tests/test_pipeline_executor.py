from core.pipeline import (
    NodeStatus,
    PipelineExecutor,
    PipelineStatus,
)


class AddOneNode:

    node_id = "add_one"
    version = "1.0"

    def run(self, context):
        return context + 1


class MultiplyNode:

    node_id = "multiply"
    version = "1.0"

    def run(self, context):
        return context * 2


class FailingNode:

    node_id = "failure"
    version = "1.0"

    def run(self, context):
        raise RuntimeError(
            "intentional failure"
        )


class InvalidOutputNode:

    node_id = "invalid_output"
    version = "1.0"

    def run(self, context):
        return -1

    def validate_output(self, result):
        return result >= 0


def test_executor_runs_nodes_in_order():

    executor = PipelineExecutor()

    result = executor.execute(
        [
            AddOneNode(),
            MultiplyNode(),
        ],
        context=2,
    )

    assert result.status == PipelineStatus.SUCCESS

    assert len(result.nodes) == 2

    assert result.nodes[0].node_id == "add_one"

    assert (
        result.nodes[0].status
        == NodeStatus.SUCCESS
    )

    assert result.nodes[0].checkpoint_id

    assert result.nodes[1].node_id == "multiply"

    assert (
        result.nodes[1].status
        == NodeStatus.SUCCESS
    )

    assert result.nodes[1].checkpoint_id


def test_executor_stops_after_failure():

    executor = PipelineExecutor()

    result = executor.execute(
        [
            AddOneNode(),
            FailingNode(),
            MultiplyNode(),
        ],
        context=2,
    )

    assert (
        result.status
        == PipelineStatus.FAILED
    )

    assert len(result.nodes) == 2

    assert (
        result.nodes[0].status
        == NodeStatus.SUCCESS
    )

    assert (
        result.nodes[1].node_id
        == "failure"
    )

    assert (
        result.nodes[1].status
        == NodeStatus.FAILED
    )

    assert result.failed_node is not None

    assert (
        result.failed_node.node_id
        == "failure"
    )

    # Failed node must NOT receive a checkpoint.
    assert (
        result.failed_node.checkpoint_id
        is None
    )


def test_executor_records_error_information():

    executor = PipelineExecutor()

    result = executor.execute(
        [FailingNode()],
        context=10,
    )

    failed = result.failed_node

    assert failed is not None

    assert (
        failed.error_type
        == "RuntimeError"
    )

    assert (
        failed.error_message
        == "intentional failure"
    )


def test_executor_generates_execution_ids():

    executor = PipelineExecutor()

    first = executor.execute(
        [AddOneNode()],
        context=1,
    )

    second = executor.execute(
        [AddOneNode()],
        context=1,
    )

    assert first.execution_id
    assert second.execution_id

    assert (
        first.execution_id
        != second.execution_id
    )


def test_executor_keeps_history():

    executor = PipelineExecutor()

    executor.execute(
        [AddOneNode()],
        context=1,
    )

    executor.execute(
        [MultiplyNode()],
        context=2,
    )

    history = executor.history()

    assert len(history) == 2

    assert (
        history[0].status
        == PipelineStatus.SUCCESS
    )

    assert (
        history[1].status
        == PipelineStatus.SUCCESS
    )


def test_last_known_good_checkpoint():

    executor = PipelineExecutor()

    result = executor.execute(
        [
            AddOneNode(),
            FailingNode(),
        ],
        context=10,
    )

    assert (
        result.status
        == PipelineStatus.FAILED
    )

    checkpoint = (
        executor.last_known_good_checkpoint(
            result.execution_id
        )
    )

    assert checkpoint is not None

    assert (
        checkpoint.node_id
        == "add_one"
    )

    assert (
        checkpoint.validation_status
        == "passed"
    )


def test_invalid_output_does_not_create_checkpoint():

    executor = PipelineExecutor()

    result = executor.execute(
        [InvalidOutputNode()],
        context=10,
    )

    assert (
        result.status
        == PipelineStatus.FAILED
    )

    assert result.failed_node is not None

    assert (
        result.failed_node.node_id
        == "invalid_output"
    )

    assert (
        result.failed_node.checkpoint_id
        is None
    )

    assert (
        executor.last_known_good_checkpoint(
            result.execution_id
        )
        is None
    )