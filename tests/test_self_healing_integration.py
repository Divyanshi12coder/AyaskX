from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.pipeline.executor import PipelineExecutor
from core.pipeline.status import NodeStatus, PipelineStatus
from core.pipeline.checkpoints.manager import CheckpointManager
from core.platform.orchestrator import AyaskXOrchestrator


# ============================================================================
# Deterministic test nodes
# ============================================================================


@dataclass
class TestContext:
    value: int = 0


class NodeA:
    node_id = "A"

    def run(self, context):
        context.value += 1
        return context


class NodeB:
    node_id = "B"

    def run(self, context):
        context.value *= 2
        return context


class FailingNodeC:
    node_id = "C"

    def run(self, context):
        raise RuntimeError("Synthetic failure at node C")


class NodeD:
    node_id = "D"

    def run(self, context):
        context.value += 10
        return context


# ============================================================================
# Helpers
# ============================================================================


def _make_executor(tmp_path: Path) -> PipelineExecutor:
    checkpoint_manager = CheckpointManager(
        root_dir=tmp_path / "checkpoints"
    )

    return PipelineExecutor(
        checkpoint_manager=checkpoint_manager
    )


def _make_failed_execution(tmp_path: Path):
    executor = _make_executor(tmp_path)

    nodes = [
        NodeA(),
        NodeB(),
        FailingNodeC(),
        NodeD(),
    ]

    execution = executor.execute(
        nodes,
        context=TestContext(),
    )

    return executor, execution


# ============================================================================
# Integration tests
# ============================================================================


def test_real_pipeline_failure_enters_self_healing_chain(tmp_path):
    """
    Real PipelineExecutor failure -> AyaskX self-healing analysis.
    """

    executor, execution = _make_failed_execution(tmp_path)

    assert execution.status == PipelineStatus.FAILED

    failed_node = execution.failed_node

    assert failed_node is not None
    assert failed_node.node_id == "C"
    assert failed_node.status == NodeStatus.FAILED

    orchestrator = AyaskXOrchestrator(
        checkpoint_manager=executor.checkpoint_manager
    )

    result = orchestrator.analyze_and_heal(
        execution
    )

    assert result is not None

    assert result["fault"] is not None
    assert result["localization"] is not None
    assert result["root_cause"] is not None
    assert result["decision"] is not None
    assert result["repair_plan"] is not None
    assert result["recovery_result"] is not None

    execution_id = execution.execution_id

    assert result["fault"].execution_id == execution_id
    assert result["localization"].execution_id == execution_id
    assert result["root_cause"].execution_id == execution_id
    assert result["decision"].execution_id == execution_id
    assert result["recovery_result"].execution_id == execution_id


def test_real_pipeline_failure_is_detected_at_c(tmp_path):
    """
    The actual failure produced by PipelineExecutor must be detected
    at node C.
    """

    executor, execution = _make_failed_execution(tmp_path)

    orchestrator = AyaskXOrchestrator(
        checkpoint_manager=executor.checkpoint_manager
    )

    result = orchestrator.analyze_and_heal(
        execution
    )

    fault = result["fault"]
    localization = result["localization"]

    assert fault.detected is True
    assert fault.observed_node == "C"

    assert localization.observed_node == "C"


def test_downstream_node_does_not_execute(tmp_path):
    """
    PipelineExecutor must stop immediately after C fails.
    """

    _, execution = _make_failed_execution(tmp_path)

    executed_node_ids = [
        node.node_id
        for node in execution.nodes
    ]

    assert "A" in executed_node_ids
    assert "B" in executed_node_ids
    assert "C" in executed_node_ids

    assert "D" not in executed_node_ids


def test_failed_execution_has_last_known_good_checkpoint(
    tmp_path,
):
    """
    Successful nodes before C should leave a valid checkpoint available.
    """

    executor, execution = _make_failed_execution(tmp_path)

    checkpoint = executor.last_known_good_checkpoint(
        execution
    )

    assert checkpoint is not None
    assert checkpoint.validation_status == "passed"

    assert checkpoint.node_id in {
        "A",
        "B",
    }


def test_self_healing_does_not_mutate_original_execution(
    tmp_path,
):
    """
    Self-healing analysis must not mutate the original failed
    PipelineExecution.
    """

    executor, execution = _make_failed_execution(tmp_path)

    original_status = execution.status
    original_nodes = execution.nodes
    original_failed_node = execution.failed_node

    orchestrator = AyaskXOrchestrator(
        checkpoint_manager=executor.checkpoint_manager
    )

    orchestrator.analyze_and_heal(
        execution
    )

    assert execution.status == original_status
    assert execution.nodes == original_nodes
    assert execution.failed_node == original_failed_node


def test_complete_real_failure_chain_is_serializable(
    tmp_path,
):
    """
    Every major self-healing domain result must expose to_dict().
    """

    executor, execution = _make_failed_execution(tmp_path)

    orchestrator = AyaskXOrchestrator(
        checkpoint_manager=executor.checkpoint_manager
    )

    result = orchestrator.analyze_and_heal(
        execution
    )

    expected_keys = (
        "fault",
        "localization",
        "root_cause",
        "decision",
        "repair_plan",
        "recovery_result",
    )

    for key in expected_keys:
        value = result[key]

        assert value is not None
        assert hasattr(value, "to_dict")

        serialized = value.to_dict()

        assert isinstance(serialized, dict)
        assert len(serialized) > 0


def test_real_failure_keeps_pipeline_failed_until_recovery(
    tmp_path,
):
    """
    Analysis itself must never silently convert the original failed
    execution into SUCCESS.
    """

    executor, execution = _make_failed_execution(tmp_path)

    orchestrator = AyaskXOrchestrator(
        checkpoint_manager=executor.checkpoint_manager
    )

    result = orchestrator.analyze_and_heal(
        execution
    )

    assert execution.status == PipelineStatus.FAILED

    assert result["fault"].detected is True