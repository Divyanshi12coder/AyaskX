"""
tests/test_root_cause.py
------------------------
Tests for RootCauseAnalyzer — deterministic, evidence-based.
No existing tests modified.
"""

from __future__ import annotations
from datetime import datetime, timezone
import pytest

from core.analysis import RootCauseAnalyzer, RootCauseReport, HypothesisCategory
from core.fault.models import FaultLocalization, FaultReport, FaultSeverity, FaultType
from core.pipeline.executor import NodeExecution, PipelineExecution
from core.pipeline.status import NodeStatus, PipelineStatus

_NOW = datetime.now(timezone.utc)


def _exec(*, execution_id="exec-001", status=PipelineStatus.FAILED):
    node = NodeExecution(
        execution_id=execution_id, node_id="node_a", status=NodeStatus.FAILED,
        started_at=_NOW, finished_at=_NOW,
        error_type="RuntimeError", error_message="test error",
    )
    return PipelineExecution(
        execution_id=execution_id, status=status, nodes=(node,),
        started_at=_NOW, finished_at=_NOW,
    )


def _fault(*, fault_type=FaultType.EXECUTION_ERROR, severity=FaultSeverity.MEDIUM,
           observed_node="node_a"):
    return FaultReport(
        execution_id="exec-001", detected=True, observed_node=observed_node,
        fault_type=fault_type, severity=severity, message="fault",
        evidence={"error_type": "RuntimeError", "error_message": "test error"},
    )


def _loc(*, probable_root_node="node_a", confidence=0.70):
    return FaultLocalization(
        execution_id="exec-001", observed_node="node_a",
        probable_root_node=probable_root_node, confidence=confidence,
        reasoning="test", evidence=(),
    )


analyzer = RootCauseAnalyzer()


def test_analyze_returns_root_cause_report():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    assert isinstance(result, RootCauseReport)


def test_report_is_frozen():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    with pytest.raises((TypeError, AttributeError)):
        result.confidence = 0.99


def test_hypotheses_are_ranked_descending():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    confs = [h.confidence for h in result.hypotheses]
    assert confs == sorted(confs, reverse=True)


def test_top_hypothesis_matches_fault_type():
    result = analyzer.analyze(
        _exec(), _fault(fault_type=FaultType.SCHEMA_MISMATCH), _loc()
    )
    top = result.top_hypothesis()
    assert top.category == HypothesisCategory.SCHEMA_MISMATCH


def test_missing_artifact_category():
    result = analyzer.analyze(
        _exec(), _fault(fault_type=FaultType.MISSING_ARTIFACT), _loc()
    )
    assert result.top_hypothesis().category == HypothesisCategory.MISSING_ARTIFACT


def test_corrupted_artifact_category():
    result = analyzer.analyze(
        _exec(), _fault(fault_type=FaultType.CORRUPTED_ARTIFACT), _loc()
    )
    assert result.top_hypothesis().category == HypothesisCategory.CORRUPTED_ARTIFACT


def test_confidence_is_bounded():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    assert 0.0 <= result.confidence <= 0.95


def test_confidence_boosted_by_high_localization():
    loc_low = _loc(confidence=0.30)
    loc_high = _loc(confidence=0.90)
    r_low = analyzer.analyze(_exec(), _fault(), loc_low)
    r_high = analyzer.analyze(_exec(), _fault(), loc_high)
    assert r_high.confidence >= r_low.confidence


def test_evidence_is_not_empty():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    assert len(result.evidence) > 0


def test_evidence_strings_are_strings():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    for e in result.evidence:
        assert isinstance(e, str)


def test_recommended_repair_categories_non_empty():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    assert len(result.recommended_repair_categories) > 0


def test_root_node_preserved():
    result = analyzer.analyze(_exec(), _fault(), _loc(probable_root_node="node_a"))
    assert result.root_node == "node_a"


def test_execution_id_preserved():
    result = analyzer.analyze(_exec(execution_id="exec-xyz"), _fault(), _loc())
    assert result.execution_id == "exec-xyz"


def test_secondary_hypotheses_present():
    result = analyzer.analyze(_exec(), _fault(fault_type=FaultType.SCHEMA_MISMATCH), _loc())
    assert len(result.hypotheses) > 1


def test_secondary_hypotheses_lower_confidence_than_primary():
    result = analyzer.analyze(_exec(), _fault(), _loc())
    primary = result.hypotheses[0].confidence
    for h in result.hypotheses[1:]:
        assert h.confidence <= primary


def test_to_dict_is_serializable():
    import json
    result = analyzer.analyze(_exec(), _fault(), _loc())
    d = result.to_dict()
    json.dumps(d)
    assert "execution_id" in d
    assert "hypotheses" in d


def test_no_fault_detected_still_produces_report():
    no_fault = FaultReport(
        execution_id="exec-001", detected=False, observed_node=None,
        fault_type=FaultType.UNKNOWN, severity=FaultSeverity.LOW,
        message="no fault", evidence={},
    )
    loc = FaultLocalization(
        execution_id="exec-001", observed_node=None, probable_root_node=None,
        confidence=1.0, reasoning="no fault", evidence=(),
    )
    exec_ = PipelineExecution(
        execution_id="exec-001", status=PipelineStatus.SUCCESS, nodes=(),
        started_at=_NOW, finished_at=_NOW,
    )
    result = analyzer.analyze(exec_, no_fault, loc)
    assert isinstance(result, RootCauseReport)
    assert result.hypotheses  # at least one hypothesis always present
