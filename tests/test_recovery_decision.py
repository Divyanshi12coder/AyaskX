"""
tests/test_recovery_decision.py
--------------------------------
Tests for RecoveryDecisionEngine — deterministic, pure-policy recovery decisions.

All tests verify that:
  1. The correct action is chosen.
  2. requires_approval has the correct value.
  3. The decision object is immutable (frozen dataclass).
  4. The engine has NO side effects on execution or fault state.

No existing tests are modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from core.fault.models import FaultLocalization, FaultReport, FaultSeverity, FaultType
from core.pipeline.executor import NodeExecution, PipelineExecution
from core.pipeline.status import NodeStatus, PipelineStatus
from core.recovery import RecoveryActionType, RecoveryDecision, RecoveryDecisionEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _execution(
    *,
    status: PipelineStatus = PipelineStatus.FAILED,
    execution_id: str = "exec-001",
) -> PipelineExecution:
    return PipelineExecution(
        execution_id=execution_id,
        status=status,
        nodes=(),
        started_at=_NOW,
        finished_at=_NOW,
    )


def _fault(
    *,
    detected: bool = True,
    observed_node: str | None = "node_a",
    fault_type: FaultType = FaultType.EXECUTION_ERROR,
    severity: FaultSeverity = FaultSeverity.MEDIUM,
    execution_id: str = "exec-001",
    error_type: str = "RuntimeError",
    error_message: str = "something failed",
) -> FaultReport:
    return FaultReport(
        execution_id=execution_id,
        detected=detected,
        observed_node=observed_node,
        fault_type=fault_type,
        severity=severity,
        message="test fault",
        evidence={
            "error_type": error_type,
            "error_message": error_message,
            "node_id": observed_node or "",
        },
    )


def _localization(
    *,
    observed_node: str | None = "node_a",
    probable_root_node: str | None = "node_a",
    confidence: float = 0.55,
    execution_id: str = "exec-001",
) -> FaultLocalization:
    return FaultLocalization(
        execution_id=execution_id,
        observed_node=observed_node,
        probable_root_node=probable_root_node,
        confidence=confidence,
        reasoning="test localization",
        evidence=(),
    )


@dataclass(frozen=True)
class _FakeCheckpoint:
    checkpoint_id: str
    node_id: str = "node_a"
    validation_status: str = "passed"


def _checkpoint(cid: str = "ckpt-001") -> _FakeCheckpoint:
    return _FakeCheckpoint(checkpoint_id=cid)


engine = RecoveryDecisionEngine()


# ---------------------------------------------------------------------------
# NO FAULT → RETRY
# ---------------------------------------------------------------------------


def test_no_fault_produces_retry():
    exec_ = _execution(status=PipelineStatus.SUCCESS)
    fault = _fault(detected=False, observed_node=None)
    loc = _localization(observed_node=None, probable_root_node=None, confidence=1.0)
    decision = engine.decide(exec_, fault, loc)
    assert decision.action == RecoveryActionType.RETRY


def test_no_fault_does_not_require_approval():
    exec_ = _execution(status=PipelineStatus.SUCCESS)
    fault = _fault(detected=False, observed_node=None)
    loc = _localization(observed_node=None, probable_root_node=None, confidence=1.0)
    decision = engine.decide(exec_, fault, loc)
    assert decision.requires_approval is False


# ---------------------------------------------------------------------------
# LOW SEVERITY → RETRY
# ---------------------------------------------------------------------------


def test_low_severity_produces_retry():
    exec_ = _execution()
    fault = _fault(severity=FaultSeverity.LOW)
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.action == RecoveryActionType.RETRY


def test_low_severity_does_not_require_approval():
    exec_ = _execution()
    fault = _fault(severity=FaultSeverity.LOW)
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.requires_approval is False


# ---------------------------------------------------------------------------
# VALIDATION_ERROR + identified node → RERUN_FROM_NODE
# ---------------------------------------------------------------------------


def test_validation_error_with_node_produces_rerun():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.VALIDATION_ERROR, severity=FaultSeverity.HIGH)
    loc = _localization(probable_root_node="node_a", confidence=0.85)
    decision = engine.decide(exec_, fault, loc)
    assert decision.action == RecoveryActionType.RERUN_FROM_NODE


def test_validation_error_rerun_targets_localized_node():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.VALIDATION_ERROR)
    loc = _localization(probable_root_node="upstream_node", confidence=0.85)
    decision = engine.decide(exec_, fault, loc)
    assert decision.target_node == "upstream_node"


def test_validation_error_rerun_does_not_require_approval():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.VALIDATION_ERROR)
    loc = _localization(probable_root_node="node_a")
    decision = engine.decide(exec_, fault, loc)
    assert decision.requires_approval is False


# ---------------------------------------------------------------------------
# SCHEMA_MISMATCH → RERUN_FROM_NODE
# ---------------------------------------------------------------------------


def test_schema_mismatch_produces_rerun():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.SCHEMA_MISMATCH, severity=FaultSeverity.HIGH)
    loc = _localization(probable_root_node="node_a", confidence=0.80)
    decision = engine.decide(exec_, fault, loc)
    assert decision.action == RecoveryActionType.RERUN_FROM_NODE


def test_schema_mismatch_rerun_does_not_require_approval():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.SCHEMA_MISMATCH)
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.requires_approval is False


# ---------------------------------------------------------------------------
# MISSING_ARTIFACT + valid checkpoint → ROLLBACK
# ---------------------------------------------------------------------------


def test_missing_artifact_with_checkpoint_produces_rollback():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.MISSING_ARTIFACT, severity=FaultSeverity.HIGH)
    loc = _localization()
    decision = engine.decide(exec_, fault, loc, last_known_good_checkpoint=_checkpoint())
    assert decision.action == RecoveryActionType.ROLLBACK


def test_rollback_requires_approval():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.MISSING_ARTIFACT)
    loc = _localization()
    decision = engine.decide(exec_, fault, loc, last_known_good_checkpoint=_checkpoint())
    assert decision.requires_approval is True


def test_rollback_carries_checkpoint_id():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.MISSING_ARTIFACT)
    loc = _localization()
    decision = engine.decide(
        exec_, fault, loc, last_known_good_checkpoint=_checkpoint("ckpt-999")
    )
    assert decision.checkpoint_id == "ckpt-999"


# ---------------------------------------------------------------------------
# MISSING_ARTIFACT + no checkpoint → ABORT
# ---------------------------------------------------------------------------


def test_missing_artifact_without_checkpoint_produces_abort():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.MISSING_ARTIFACT)
    loc = _localization()
    decision = engine.decide(exec_, fault, loc, last_known_good_checkpoint=None)
    assert decision.action == RecoveryActionType.ABORT


def test_abort_requires_approval():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.MISSING_ARTIFACT)
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.requires_approval is True


# ---------------------------------------------------------------------------
# CORRUPTED_ARTIFACT + security hint → QUARANTINE
# ---------------------------------------------------------------------------


def test_corrupted_artifact_security_error_type_produces_quarantine():
    exec_ = _execution()
    fault = _fault(
        fault_type=FaultType.CORRUPTED_ARTIFACT,
        severity=FaultSeverity.CRITICAL,
        error_type="SecurityError",
        error_message="artifact tampered",
    )
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.action == RecoveryActionType.QUARANTINE


def test_quarantine_requires_approval():
    exec_ = _execution()
    fault = _fault(
        fault_type=FaultType.CORRUPTED_ARTIFACT,
        severity=FaultSeverity.CRITICAL,
        error_type="SecurityError",
        error_message="tampered",
    )
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.requires_approval is True


def test_corrupted_artifact_with_integrity_keyword_produces_quarantine():
    exec_ = _execution()
    fault = _fault(
        fault_type=FaultType.CORRUPTED_ARTIFACT,
        severity=FaultSeverity.CRITICAL,
        error_type="RuntimeError",
        error_message="integrity check failed on artifact",
    )
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.action == RecoveryActionType.QUARANTINE


# ---------------------------------------------------------------------------
# CRITICAL + UNKNOWN → MANUAL_REVIEW
# ---------------------------------------------------------------------------


def test_critical_unknown_fault_produces_manual_review():
    exec_ = _execution()
    fault = _fault(
        fault_type=FaultType.UNKNOWN,
        severity=FaultSeverity.CRITICAL,
    )
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.action == RecoveryActionType.MANUAL_REVIEW


def test_manual_review_requires_approval():
    exec_ = _execution()
    fault = _fault(
        fault_type=FaultType.UNKNOWN,
        severity=FaultSeverity.CRITICAL,
    )
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.requires_approval is True


def test_critical_execution_error_produces_manual_review():
    exec_ = _execution()
    fault = _fault(
        fault_type=FaultType.EXECUTION_ERROR,
        severity=FaultSeverity.CRITICAL,
    )
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    # CRITICAL severity → MANUAL_REVIEW (before EXECUTION_ERROR rollback rule)
    assert decision.action == RecoveryActionType.MANUAL_REVIEW


# ---------------------------------------------------------------------------
# IMMUTABILITY + NO SIDE EFFECTS
# ---------------------------------------------------------------------------


def test_decision_is_immutable():
    exec_ = _execution()
    fault = _fault()
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    with pytest.raises((TypeError, AttributeError)):
        decision.action = RecoveryActionType.RETRY  # type: ignore[misc]


def test_decision_does_not_mutate_execution():
    exec_ = _execution()
    original_status = exec_.status
    original_node_count = len(exec_.nodes)
    fault = _fault()
    loc = _localization()
    engine.decide(exec_, fault, loc)
    assert exec_.status == original_status
    assert len(exec_.nodes) == original_node_count


def test_decision_does_not_mutate_fault():
    exec_ = _execution()
    fault = _fault(fault_type=FaultType.MISSING_ARTIFACT)
    original_type = fault.fault_type
    loc = _localization()
    engine.decide(exec_, fault, loc)
    assert fault.fault_type == original_type


def test_decision_execution_id_matches_pipeline():
    exec_ = _execution(execution_id="exec-abc")
    fault = _fault(execution_id="exec-abc")
    loc = _localization(execution_id="exec-abc")
    decision = engine.decide(exec_, fault, loc)
    assert decision.execution_id == "exec-abc"


def test_decision_reason_is_non_empty():
    exec_ = _execution()
    fault = _fault()
    loc = _localization()
    decision = engine.decide(exec_, fault, loc)
    assert decision.reason
    assert len(decision.reason) > 0
