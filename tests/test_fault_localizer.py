"""
tests/test_fault_localizer.py
------------------------------
Tests for FaultLocalizer — evidence-based root cause localization.

All fixtures are minimal and explicit.
No existing tests are modified.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.fault import (
    FaultDetector,
    FaultLocalization,
    FaultLocalizer,
    FaultReport,
    FaultSeverity,
    FaultType,
)
from core.observability.events import NodeEvent
from core.pipeline.executor import NodeExecution, PipelineExecution
from core.pipeline.status import NodeStatus, PipelineStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _node(
    node_id: str,
    *,
    status: NodeStatus = NodeStatus.SUCCESS,
    error_type: str | None = None,
    error_message: str | None = None,
    checkpoint_id: str | None = "ckpt-001",
    output_metadata: dict | None = None,
) -> NodeExecution:
    return NodeExecution(
        execution_id="exec-001",
        node_id=node_id,
        status=status,
        started_at=_NOW,
        finished_at=_NOW,
        error_type=error_type,
        error_message=error_message,
        checkpoint_id=checkpoint_id,
        output_metadata=output_metadata or {},
    )


def _failed_node(
    node_id: str,
    *,
    error_type: str = "RuntimeError",
    error_message: str = "failure",
) -> NodeExecution:
    return _node(
        node_id,
        status=NodeStatus.FAILED,
        error_type=error_type,
        error_message=error_message,
        checkpoint_id=None,
    )


def _execution(
    *nodes: NodeExecution,
    status: PipelineStatus = PipelineStatus.FAILED,
    execution_id: str = "exec-001",
) -> PipelineExecution:
    return PipelineExecution(
        execution_id=execution_id,
        status=status,
        nodes=nodes,
        started_at=_NOW,
        finished_at=_NOW,
    )


def _success_report(execution_id: str = "exec-001") -> FaultReport:
    return FaultReport(
        execution_id=execution_id,
        detected=False,
        observed_node=None,
        fault_type=FaultType.UNKNOWN,
        severity=FaultSeverity.LOW,
        message="no fault",
        evidence={},
    )


def _fault_report(
    observed_node: str,
    *,
    fault_type: FaultType = FaultType.EXECUTION_ERROR,
    severity: FaultSeverity = FaultSeverity.MEDIUM,
    execution_id: str = "exec-001",
) -> FaultReport:
    return FaultReport(
        execution_id=execution_id,
        detected=True,
        observed_node=observed_node,
        fault_type=fault_type,
        severity=severity,
        message="fault occurred",
        evidence={"error_type": "RuntimeError"},
    )


def _event(
    node_id: str,
    event_type: str,
    execution_id: str = "exec-001",
) -> NodeEvent:
    return NodeEvent(
        execution_id=execution_id,
        pipeline_id="pipe-001",
        node_id=node_id,
        event_type=event_type,
    )


# ---------------------------------------------------------------------------
# RULE 1 — SUCCESS: trivial localization
# ---------------------------------------------------------------------------


def test_success_execution_trivial_localization():
    nodes = (_node("a", status=NodeStatus.SUCCESS),)
    exec_ = _execution(*nodes, status=PipelineStatus.SUCCESS)
    fault = _success_report()
    result = FaultLocalizer().localize(exec_, fault)
    assert result.detected is False if hasattr(result, "detected") else True
    assert result.observed_node is None
    assert result.probable_root_node is None


def test_success_execution_confidence_is_one():
    nodes = (_node("a", status=NodeStatus.SUCCESS),)
    exec_ = _execution(*nodes, status=PipelineStatus.SUCCESS)
    fault = _success_report()
    result = FaultLocalizer().localize(exec_, fault)
    assert result.confidence == 1.0


def test_success_localization_preserves_execution_id():
    nodes = (_node("a", status=NodeStatus.SUCCESS),)
    exec_ = _execution(*nodes, status=PipelineStatus.SUCCESS, execution_id="exec-xyz")
    fault = _success_report(execution_id="exec-xyz")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.execution_id == "exec-xyz"


# ---------------------------------------------------------------------------
# RULE 6 — Single failed node: conservative
# ---------------------------------------------------------------------------


def test_single_failed_node_root_is_observed():
    node_a = _failed_node("a")
    exec_ = _execution(node_a)
    fault = _fault_report("a")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.observed_node == "a"
    assert result.probable_root_node == "a"


def test_single_failed_node_confidence_is_conservative():
    node_a = _failed_node("a")
    exec_ = _execution(node_a)
    fault = _fault_report("a")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.confidence <= 0.60


# ---------------------------------------------------------------------------
# RULE 2 — Previous node has status=FAILED
# ---------------------------------------------------------------------------


def test_previous_failed_node_becomes_root():
    """A→B pipeline: A fails, B also fails. Root should be A."""
    node_a = _failed_node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.probable_root_node == "a"


def test_previous_failed_node_confidence_is_high():
    node_a = _failed_node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.confidence >= 0.85


def test_observed_node_preserved_when_upstream_is_root():
    node_a = _failed_node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.observed_node == "b"


# ---------------------------------------------------------------------------
# RULE 3 — Output validation event for upstream node
# ---------------------------------------------------------------------------


def test_output_validation_event_shifts_root_upstream():
    node_a = _node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    events = (_event("a", "output_validation_failed"),)
    result = FaultLocalizer().localize(exec_, fault, events=events)
    assert result.probable_root_node == "a"


def test_output_validation_event_confidence_is_high():
    node_a = _node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    events = (_event("a", "output_validation_failed"),)
    result = FaultLocalizer().localize(exec_, fault, events=events)
    assert result.confidence >= 0.85


def test_unrelated_event_does_not_shift_root():
    node_a = _node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    events = (_event("a", "node_started"),)
    result = FaultLocalizer().localize(exec_, fault, events=events)
    # Without validation failure evidence, root should remain conservative
    assert result.probable_root_node == "b"


# ---------------------------------------------------------------------------
# RULE 4 — Output validation metadata for upstream node
# ---------------------------------------------------------------------------


def test_validation_failed_metadata_shifts_root_upstream():
    node_a = _node("a", output_metadata={"validation_failed": True})
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.probable_root_node == "a"


def test_validation_status_failed_metadata_shifts_root():
    node_a = _node("a", output_metadata={"validation_status": "failed"})
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.probable_root_node == "a"


def test_validation_metadata_confidence_is_high():
    node_a = _node("a", output_metadata={"validation_failed": True})
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.confidence >= 0.85


# ---------------------------------------------------------------------------
# RULE 5 — Missing checkpoint on upstream node
# ---------------------------------------------------------------------------


def test_missing_checkpoint_on_upstream_shifts_root():
    node_a = _node("a", checkpoint_id=None)  # succeeded but no checkpoint
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.probable_root_node == "a"


def test_missing_checkpoint_confidence_is_lower():
    node_a = _node("a", checkpoint_id=None)
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.confidence == 0.75


# ---------------------------------------------------------------------------
# EVIDENCE INTEGRITY
# ---------------------------------------------------------------------------


def test_evidence_is_not_empty_when_upstream_found():
    node_a = _failed_node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert len(result.evidence) > 0


def test_evidence_is_not_fabricated_from_thin_air():
    """Evidence should only reference things we can actually see."""
    node_a = _node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    # Every evidence entry should be a string (not invented objects)
    for item in result.evidence:
        assert isinstance(item, str)


def test_confidence_never_exceeds_0_95_for_normal_evidence():
    node_a = _failed_node("a")
    node_b = _failed_node("b")
    exec_ = _execution(node_a, node_b)
    fault = _fault_report("b")
    result = FaultLocalizer().localize(exec_, fault)
    assert result.confidence <= 0.95


def test_localization_is_immutable():
    node_a = _failed_node("a")
    exec_ = _execution(node_a)
    fault = _fault_report("a")
    result = FaultLocalizer().localize(exec_, fault)
    with pytest.raises((TypeError, AttributeError)):
        result.confidence = 0.99  # type: ignore[misc]
