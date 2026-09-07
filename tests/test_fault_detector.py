"""
tests/test_fault_detector.py
-----------------------------
Tests for FaultDetector — deterministic fault classification.

All tests are self-contained and use minimal, explicit fixtures.
No existing tests are modified.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.fault import FaultDetector, FaultReport, FaultSeverity, FaultType
from core.pipeline.executor import NodeExecution, PipelineExecution
from core.pipeline.status import NodeStatus, PipelineStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_pipeline_execution(
    *,
    status: PipelineStatus = PipelineStatus.SUCCESS,
    nodes: tuple = (),
    execution_id: str = "exec-001",
) -> PipelineExecution:
    return PipelineExecution(
        execution_id=execution_id,
        status=status,
        nodes=nodes,
        started_at=_NOW,
        finished_at=_NOW,
    )


def _make_node_execution(
    *,
    node_id: str = "node_a",
    status: NodeStatus = NodeStatus.FAILED,
    error_type: str | None = None,
    error_message: str | None = None,
    checkpoint_id: str | None = None,
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
    )


def _failed_pipeline(
    node_id: str = "node_a",
    error_type: str = "RuntimeError",
    error_message: str = "something went wrong",
) -> PipelineExecution:
    node = _make_node_execution(
        node_id=node_id,
        status=NodeStatus.FAILED,
        error_type=error_type,
        error_message=error_message,
    )
    return _make_pipeline_execution(
        status=PipelineStatus.FAILED,
        nodes=(node,),
    )


# ---------------------------------------------------------------------------
# BASIC DETECTION
# ---------------------------------------------------------------------------


def test_successful_pipeline_produces_no_fault():
    execution = _make_pipeline_execution(status=PipelineStatus.SUCCESS)
    report = FaultDetector().detect(execution)
    assert report.detected is False


def test_successful_pipeline_has_no_observed_node():
    execution = _make_pipeline_execution(status=PipelineStatus.SUCCESS)
    report = FaultDetector().detect(execution)
    assert report.observed_node is None


def test_failed_pipeline_is_detected():
    execution = _failed_pipeline()
    report = FaultDetector().detect(execution)
    assert report.detected is True


def test_failed_node_id_preserved_as_observed_node():
    execution = _failed_pipeline(node_id="my_node")
    report = FaultDetector().detect(execution)
    assert report.observed_node == "my_node"


def test_execution_id_preserved():
    node = _make_node_execution(status=NodeStatus.FAILED, error_type="RuntimeError")
    execution = _make_pipeline_execution(
        status=PipelineStatus.FAILED,
        nodes=(node,),
        execution_id="exec-xyz",
    )
    report = FaultDetector().detect(execution)
    assert report.execution_id == "exec-xyz"


# ---------------------------------------------------------------------------
# KEYERROR → SCHEMA_MISMATCH
# ---------------------------------------------------------------------------


def test_keyerror_with_column_classified_as_schema_mismatch():
    execution = _failed_pipeline(
        error_type="KeyError",
        error_message="'target_column' not found",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.SCHEMA_MISMATCH


def test_keyerror_with_column_is_high_severity():
    execution = _failed_pipeline(
        error_type="KeyError",
        error_message="missing column 'price'",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.HIGH


def test_generic_keyerror_classified_as_schema_mismatch():
    execution = _failed_pipeline(
        error_type="KeyError",
        error_message="'my_key'",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.SCHEMA_MISMATCH


def test_generic_keyerror_is_medium_severity():
    execution = _failed_pipeline(
        error_type="KeyError",
        error_message="'my_key'",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.MEDIUM


# ---------------------------------------------------------------------------
# FILENOTFOUNDERROR → MISSING_ARTIFACT
# ---------------------------------------------------------------------------


def test_filenotfounderror_classified_as_missing_artifact():
    execution = _failed_pipeline(
        error_type="FileNotFoundError",
        error_message="No such file: artifacts/model.pkl",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.MISSING_ARTIFACT


def test_filenotfounderror_is_high_severity():
    execution = _failed_pipeline(
        error_type="FileNotFoundError",
        error_message="artifacts/model.pkl not found",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.HIGH


# ---------------------------------------------------------------------------
# VALUEERROR → VALIDATION_ERROR
# ---------------------------------------------------------------------------


def test_output_validation_valueerror_classified_correctly():
    execution = _failed_pipeline(
        error_type="ValueError",
        error_message="Node output validation failed.",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.VALIDATION_ERROR


def test_output_validation_valueerror_is_high_severity():
    execution = _failed_pipeline(
        error_type="ValueError",
        error_message="Node output validation failed.",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.HIGH


def test_generic_validation_valueerror_is_medium_severity():
    execution = _failed_pipeline(
        error_type="ValueError",
        error_message="validation check failed for column",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.VALIDATION_ERROR
    assert report.severity == FaultSeverity.MEDIUM


# ---------------------------------------------------------------------------
# TIMEOUTERROR → TIMEOUT
# ---------------------------------------------------------------------------


def test_timeouterror_classified_as_timeout():
    execution = _failed_pipeline(
        error_type="TimeoutError",
        error_message="Node exceeded 30s time limit",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.TIMEOUT


def test_timeouterror_is_high_severity():
    execution = _failed_pipeline(
        error_type="TimeoutError",
        error_message="timed out",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.HIGH


# ---------------------------------------------------------------------------
# MEMORYERROR → RESOURCE_ERROR / CRITICAL
# ---------------------------------------------------------------------------


def test_memoryerror_classified_as_resource_error():
    execution = _failed_pipeline(
        error_type="MemoryError",
        error_message="",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.RESOURCE_ERROR


def test_memoryerror_is_critical_severity():
    execution = _failed_pipeline(
        error_type="MemoryError",
        error_message="",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.CRITICAL


# ---------------------------------------------------------------------------
# RUNTIMEERROR → EXECUTION_ERROR / DEPENDENCY_FAILURE
# ---------------------------------------------------------------------------


def test_runtimeerror_classified_as_execution_error():
    execution = _failed_pipeline(
        error_type="RuntimeError",
        error_message="intentional failure",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.EXECUTION_ERROR


def test_runtimeerror_is_medium_severity():
    execution = _failed_pipeline(
        error_type="RuntimeError",
        error_message="intentional failure",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.MEDIUM


def test_dependency_runtimeerror_classified_as_dependency_failure():
    execution = _failed_pipeline(
        error_type="RuntimeError",
        error_message="upstream dependency failed to produce output",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.DEPENDENCY_FAILURE


def test_dependency_failure_is_high_severity():
    execution = _failed_pipeline(
        error_type="RuntimeError",
        error_message="dependency not resolved",
    )
    report = FaultDetector().detect(execution)
    assert report.severity == FaultSeverity.HIGH


# ---------------------------------------------------------------------------
# UNKNOWN ERROR
# ---------------------------------------------------------------------------


def test_unknown_error_type_produces_execution_error_or_unknown():
    execution = _failed_pipeline(
        error_type="SomeRandomCustomError",
        error_message="something exotic",
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type in (FaultType.EXECUTION_ERROR, FaultType.UNKNOWN)


def test_no_error_type_produces_unknown():
    node = _make_node_execution(
        status=NodeStatus.FAILED,
        error_type=None,
        error_message=None,
    )
    execution = _make_pipeline_execution(
        status=PipelineStatus.FAILED,
        nodes=(node,),
    )
    report = FaultDetector().detect(execution)
    assert report.fault_type == FaultType.UNKNOWN


# ---------------------------------------------------------------------------
# EVIDENCE POPULATION
# ---------------------------------------------------------------------------


def test_evidence_is_populated_from_execution_data():
    execution = _failed_pipeline(
        node_id="transform_node",
        error_type="RuntimeError",
        error_message="intentional failure",
    )
    report = FaultDetector().detect(execution)
    assert "error_type" in report.evidence
    assert report.evidence["error_type"] == "RuntimeError"


def test_evidence_contains_node_id():
    execution = _failed_pipeline(
        node_id="special_node",
        error_type="RuntimeError",
        error_message="failure",
    )
    report = FaultDetector().detect(execution)
    assert report.evidence.get("node_id") == "special_node"


def test_evidence_is_not_fabricated_on_success():
    execution = _make_pipeline_execution(status=PipelineStatus.SUCCESS)
    report = FaultDetector().detect(execution)
    # Evidence dict should be empty (nothing to fabricate)
    assert report.evidence == {}


# ---------------------------------------------------------------------------
# DETERMINISM
# ---------------------------------------------------------------------------


def test_detector_is_deterministic():
    """Same input must always produce same output."""
    execution = _failed_pipeline(
        error_type="KeyError",
        error_message="'missing_column'",
    )
    detector = FaultDetector()
    report1 = detector.detect(execution)
    report2 = detector.detect(execution)
    assert report1.fault_type == report2.fault_type
    assert report1.severity == report2.severity


def test_report_is_immutable():
    """FaultReport is a frozen dataclass."""
    execution = _failed_pipeline()
    report = FaultDetector().detect(execution)
    with pytest.raises((TypeError, AttributeError)):
        report.detected = False  # type: ignore[misc]
