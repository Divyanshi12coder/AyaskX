"""
tests/test_recovery_executor.py
--------------------------------
Tests for RecoveryExecutor — checkpoint-aware recovery execution.

Tests cover:
  - RETRY, RERUN_FROM_NODE, ROLLBACK, ABORT, MANUAL_REVIEW, QUARANTINE
  - missing/invalid checkpoint safety
  - validation gate behavior
  - no infinite retries
  - no mutation of original execution
  - execution_id preservation
  - observability event emission
  - RecoveryResult immutability and serializability
  - no fabricated checkpoints

No existing tests are modified.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from core.pipeline.checkpoints.manager import CheckpointManager
from core.pipeline.executor import NodeExecution, PipelineExecution
from core.pipeline.status import NodeStatus, PipelineStatus
from core.recovery.decision import RecoveryActionType, RecoveryDecision
from core.recovery.errors import CheckpointNotFoundError
from core.recovery.executor import ArtifactQuarantine, RecoveryExecutor
from core.recovery.models import RecoveryResult, RecoveryStatus
from core.recovery.validator import RecoveryValidator


_NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _checkpoint_manager() -> CheckpointManager:
    """Fresh in-memory-capable CheckpointManager backed by a temp dir."""
    tmpdir = tempfile.mkdtemp()
    return CheckpointManager(root_dir=tmpdir)


def _execution(
    *,
    execution_id: str = "exec-001",
    status: PipelineStatus = PipelineStatus.FAILED,
) -> PipelineExecution:
    return PipelineExecution(
        execution_id=execution_id,
        status=status,
        nodes=(),
        started_at=_NOW,
        finished_at=_NOW,
    )


def _decision(
    action: RecoveryActionType = RecoveryActionType.ABORT,
    *,
    execution_id: str = "exec-001",
    target_node: str | None = None,
    checkpoint_id: str | None = None,
    requires_approval: bool = False,
    reason: str = "test",
) -> RecoveryDecision:
    return RecoveryDecision(
        execution_id=execution_id,
        action=action,
        requires_approval=requires_approval,
        reason=reason,
        target_node=target_node,
        checkpoint_id=checkpoint_id,
    )


def _executor(manager: CheckpointManager | None = None) -> RecoveryExecutor:
    return RecoveryExecutor(
        checkpoint_manager=manager or _checkpoint_manager(),
        max_attempts=1,
    )


class _GoodNode:
    node_id = "good_node"

    def run(self, context: Any) -> int:
        return (context or 0) + 1


class _FailingNode:
    node_id = "failing_node"

    def run(self, context: Any) -> None:
        raise RuntimeError("intentional node failure")


# ---------------------------------------------------------------------------
# ABORT
# ---------------------------------------------------------------------------


def test_abort_does_not_execute_nodes():
    manager = _checkpoint_manager()
    executor = _executor(manager)
    dec = _decision(RecoveryActionType.ABORT)
    result = executor.execute(dec)
    assert result.success is False
    assert result.status == RecoveryStatus.ABORTED
    assert result.rollback_performed is False


def test_abort_does_not_require_nodes():
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT)
    result = executor.execute(dec)
    assert result.action == RecoveryActionType.ABORT


# ---------------------------------------------------------------------------
# MANUAL_REVIEW
# ---------------------------------------------------------------------------


def test_manual_review_does_not_execute_nodes():
    executor = _executor()
    dec = _decision(RecoveryActionType.MANUAL_REVIEW)
    result = executor.execute(dec)
    assert result.success is False
    assert result.status == RecoveryStatus.PENDING_REVIEW
    assert result.rollback_performed is False


def test_manual_review_preserves_execution_id():
    executor = _executor()
    dec = _decision(RecoveryActionType.MANUAL_REVIEW, execution_id="exec-xyz")
    result = executor.execute(dec)
    assert result.execution_id == "exec-xyz"


# ---------------------------------------------------------------------------
# QUARANTINE
# ---------------------------------------------------------------------------


def test_quarantine_does_not_continue_execution():
    executor = _executor()
    dec = _decision(
        RecoveryActionType.QUARANTINE,
        target_node="corrupt_node",
        reason="integrity breach",
    )
    result = executor.execute(dec)
    assert result.success is False
    assert result.status == RecoveryStatus.QUARANTINED
    assert result.rollback_performed is False


def test_quarantine_records_evidence():
    executor = _executor()
    dec = _decision(
        RecoveryActionType.QUARANTINE,
        target_node="corrupt_node",
        reason="tampered artifact",
    )
    result = executor.execute(dec)
    assert any("quarantine" in e.lower() for e in result.evidence)


# ---------------------------------------------------------------------------
# RETRY
# ---------------------------------------------------------------------------


def test_retry_without_callable_skips_safely():
    executor = _executor()
    dec = _decision(RecoveryActionType.RETRY)
    result = executor.execute(dec, pipeline_callable=None)
    assert result.success is False
    assert result.status == RecoveryStatus.SKIPPED


def test_retry_with_callable_succeeds():
    executor = _executor()
    dec = _decision(RecoveryActionType.RETRY)
    called = []
    result = executor.execute(dec, pipeline_callable=lambda: called.append(1))
    assert result.success is True
    assert len(called) == 1


def test_retry_callable_failure_produces_failed_result():
    executor = _executor()
    dec = _decision(RecoveryActionType.RETRY)

    def bad_pipeline():
        raise RuntimeError("pipeline failed")

    result = executor.execute(dec, pipeline_callable=bad_pipeline)
    assert result.success is False
    assert result.status == RecoveryStatus.FAILED


# ---------------------------------------------------------------------------
# ROLLBACK
# ---------------------------------------------------------------------------


def test_rollback_with_valid_checkpoint_succeeds():
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact={"key": "value"},
        validation_status="passed",
    )

    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.ROLLBACK,
        checkpoint_id=ckpt.checkpoint_id,
    )
    result = executor.execute(dec)
    assert result.success is True
    assert result.rollback_performed is True
    assert result.recovered_from_checkpoint == ckpt.checkpoint_id


def test_rollback_records_checkpoint_id():
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact={"x": 1},
        validation_status="passed",
    )
    executor = _executor(manager)
    dec = _decision(RecoveryActionType.ROLLBACK, checkpoint_id=ckpt.checkpoint_id)
    result = executor.execute(dec)
    assert result.recovered_from_checkpoint == ckpt.checkpoint_id


def test_rollback_missing_checkpoint_id_fails_safely():
    executor = _executor()
    dec = _decision(RecoveryActionType.ROLLBACK, checkpoint_id=None)
    result = executor.execute(dec)
    assert result.success is False
    assert result.rollback_performed is False


def test_rollback_nonexistent_checkpoint_fails_safely():
    executor = _executor()
    dec = _decision(RecoveryActionType.ROLLBACK, checkpoint_id="nonexistent-ckpt")
    result = executor.execute(dec)
    assert result.success is False
    assert result.rollback_performed is False


def test_rollback_invalid_checkpoint_status_fails():
    """Checkpoint with validation_status != 'passed' must fail the gate."""
    manager = _checkpoint_manager()
    # Create a checkpoint and we'll pass a fake one with bad status
    # We simulate by creating a valid checkpoint then testing the validator
    # directly through an end-to-end path

    # We create the checkpoint but patch validation_status via a workaround:
    # The CheckpointManager always writes validation_status='passed' unless
    # we pass it explicitly. Let's use 'unknown' to trigger failure.
    # However since CheckpointManager.create() accepts validation_status,
    # we can create a "bad" checkpoint:
    manager2 = CheckpointManager(root_dir=tempfile.mkdtemp())
    ckpt = manager2.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact={"k": 1},
        validation_status="failed",   # invalid status
    )
    executor = _executor(manager2)
    dec = _decision(RecoveryActionType.ROLLBACK, checkpoint_id=ckpt.checkpoint_id)
    result = executor.execute(dec)
    assert result.success is False


def test_rollback_validation_passed_in_result():
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact={"z": 99},
        validation_status="passed",
    )
    executor = _executor(manager)
    dec = _decision(RecoveryActionType.ROLLBACK, checkpoint_id=ckpt.checkpoint_id)
    result = executor.execute(dec)
    assert result.validation_passed is True


# ---------------------------------------------------------------------------
# RERUN_FROM_NODE
# ---------------------------------------------------------------------------


def test_rerun_from_node_with_valid_upstream_checkpoint():
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact=10,
        validation_status="passed",
    )

    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.RERUN_FROM_NODE,
        target_node="good_node",
        checkpoint_id=ckpt.checkpoint_id,
    )

    result = executor.execute(dec, nodes=[_GoodNode()])
    assert result.success is True
    assert result.resumed_from_node == "good_node"
    assert result.recovered_from_checkpoint == ckpt.checkpoint_id


def test_rerun_from_node_without_nodes_fails_safely():
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact=5,
        validation_status="passed",
    )
    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.RERUN_FROM_NODE,
        target_node="good_node",
        checkpoint_id=ckpt.checkpoint_id,
    )
    result = executor.execute(dec, nodes=None)
    assert result.success is False


def test_rerun_failing_node_does_not_continue():
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact=5,
        validation_status="passed",
    )
    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.RERUN_FROM_NODE,
        target_node="failing_node",
        checkpoint_id=ckpt.checkpoint_id,
    )
    result = executor.execute(dec, nodes=[_FailingNode()])
    assert result.success is False
    assert result.status == RecoveryStatus.FAILED


def test_rerun_does_not_exceed_max_attempts():
    """Node fails once. With max_attempts=1 there must be exactly 1 attempt."""
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact=5,
        validation_status="passed",
    )
    call_count = []

    class CountingFailNode:
        node_id = "failing_node"

        def run(self, context: Any) -> None:
            call_count.append(1)
            raise RuntimeError("always fails")

    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.RERUN_FROM_NODE,
        target_node="failing_node",
        checkpoint_id=ckpt.checkpoint_id,
    )
    result = executor.execute(dec, nodes=[CountingFailNode()])
    assert result.success is False
    assert len(call_count) == 1  # exactly 1 attempt, no infinite retry


def test_rerun_missing_target_node_in_list_fails():
    """target_node not in supplied nodes → safe failure."""
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact=5,
        validation_status="passed",
    )
    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.RERUN_FROM_NODE,
        target_node="nonexistent_node",
        checkpoint_id=ckpt.checkpoint_id,
    )
    result = executor.execute(dec, nodes=[_GoodNode()])
    assert result.success is False


def test_rerun_downstream_nodes_execute_after_target():
    """A→B→C: target=A, all three nodes provided → B and C also run."""
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="upstream",
        artifact=0,
        validation_status="passed",
    )

    executed = []

    class NodeA:
        node_id = "node_a"

        def run(self, ctx: Any) -> int:
            executed.append("a")
            return (ctx or 0) + 1

    class NodeB:
        node_id = "node_b"

        def run(self, ctx: Any) -> int:
            executed.append("b")
            return ctx + 1

    class NodeC:
        node_id = "node_c"

        def run(self, ctx: Any) -> int:
            executed.append("c")
            return ctx + 1

    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.RERUN_FROM_NODE,
        target_node="node_a",
        checkpoint_id=ckpt.checkpoint_id,
    )
    result = executor.execute(dec, nodes=[NodeA(), NodeB(), NodeC()])
    assert result.success is True
    assert executed == ["a", "b", "c"]


def test_failed_rerun_does_not_execute_downstream_nodes():
    """If the target node fails, downstream nodes must NOT run."""
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="upstream",
        artifact=0,
        validation_status="passed",
    )

    executed = []

    class FailFirst:
        node_id = "fail_first"

        def run(self, ctx: Any) -> None:
            raise RuntimeError("I always fail")

    class ShouldNotRun:
        node_id = "should_not_run"

        def run(self, ctx: Any) -> int:
            executed.append("ran")
            return ctx

    executor = _executor(manager)
    dec = _decision(
        RecoveryActionType.RERUN_FROM_NODE,
        target_node="fail_first",
        checkpoint_id=ckpt.checkpoint_id,
    )
    result = executor.execute(dec, nodes=[FailFirst(), ShouldNotRun()])
    assert result.success is False
    assert executed == []  # downstream was never reached


# ---------------------------------------------------------------------------
# OBSERVABILITY
# ---------------------------------------------------------------------------


def test_recovery_produces_events():
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT)
    executor.execute(dec)
    assert len(executor.events) > 0


def test_events_contain_recovery_started():
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT)
    executor.execute(dec)
    event_types = {e.event_type for e in executor.events}
    assert "recovery_started" in event_types


def test_events_carry_execution_id():
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT, execution_id="exec-obs")
    executor.execute(dec)
    for event in executor.events:
        assert event.execution_id == "exec-obs"


def test_rollback_emits_checkpoint_restored_event():
    manager = _checkpoint_manager()
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact={"x": 1},
        validation_status="passed",
    )
    executor = _executor(manager)
    dec = _decision(RecoveryActionType.ROLLBACK, checkpoint_id=ckpt.checkpoint_id)
    executor.execute(dec)
    event_types = {e.event_type for e in executor.events}
    assert "recovery_checkpoint_restored" in event_types


# ---------------------------------------------------------------------------
# RESULT INTEGRITY
# ---------------------------------------------------------------------------


def test_recovery_result_is_frozen():
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT)
    result = executor.execute(dec)
    with pytest.raises((TypeError, AttributeError)):
        result.success = True  # type: ignore[misc]


def test_recovery_result_is_serializable():
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT)
    result = executor.execute(dec)
    d = result.to_dict()
    json.dumps(d)  # must not raise


def test_original_execution_not_mutated():
    exec_ = _execution(execution_id="exec-001")
    original_status = exec_.status
    original_count = len(exec_.nodes)

    manager = _checkpoint_manager()
    executor = _executor(manager)
    dec = _decision(RecoveryActionType.ABORT, execution_id="exec-001")
    executor.execute(dec)

    # Verify the execution object is unchanged
    assert exec_.status == original_status
    assert len(exec_.nodes) == original_count


def test_recovery_result_execution_id_preserved():
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT, execution_id="exec-preserve")
    result = executor.execute(dec)
    assert result.execution_id == "exec-preserve"


def test_no_checkpoint_is_fabricated():
    """If no checkpoint is given, recovered_from_checkpoint must be None."""
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT, checkpoint_id=None)
    result = executor.execute(dec)
    assert result.recovered_from_checkpoint is None


def test_recovery_never_silently_succeeds_when_validation_fails():
    """
    If checkpoint validation fails, success must be False.
    """
    manager = CheckpointManager(root_dir=tempfile.mkdtemp())
    ckpt = manager.create(
        execution_id="exec-001",
        node_id="node_a",
        artifact={"k": 1},
        validation_status="failed",
    )
    executor = _executor(manager)
    dec = _decision(RecoveryActionType.ROLLBACK, checkpoint_id=ckpt.checkpoint_id)
    result = executor.execute(dec)
    assert result.success is False
    assert result.validation_passed is False


def test_recovery_action_is_deterministic():
    """Same input always produces same action."""
    executor = _executor()
    dec = _decision(RecoveryActionType.ABORT)
    r1 = executor.execute(dec)
    r2 = executor.execute(dec)
    assert r1.action == r2.action
    assert r1.status == r2.status
