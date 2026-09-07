"""
tests/test_monitoring.py
------------------------
Tests for PipelineMonitor — structured, configurable alerts.
No existing tests modified.
"""
from __future__ import annotations
import json
import pytest
from datetime import datetime, timezone

from core.monitoring import PipelineMonitor, MonitoringConfig, AlertCategory, AlertSeverity
from core.pipeline.executor import NodeExecution, PipelineExecution
from core.pipeline.status import NodeStatus, PipelineStatus

_NOW = datetime.now(timezone.utc)


def _failed_exec():
    node = NodeExecution(
        execution_id="exec-001", node_id="bad_node", status=NodeStatus.FAILED,
        started_at=_NOW, finished_at=_NOW,
        error_type="RuntimeError", error_message="exploded",
    )
    return PipelineExecution(
        execution_id="exec-001", status=PipelineStatus.FAILED,
        nodes=(node,), started_at=_NOW, finished_at=_NOW,
    )


def _success_exec():
    node = NodeExecution(
        execution_id="exec-001", node_id="good_node", status=NodeStatus.SUCCESS,
        started_at=_NOW, finished_at=_NOW,
    )
    return PipelineExecution(
        execution_id="exec-001", status=PipelineStatus.SUCCESS,
        nodes=(node,), started_at=_NOW, finished_at=_NOW,
    )


def test_failed_execution_raises_alert():
    m = PipelineMonitor()
    m.check_execution(_failed_exec())
    assert len(m.alerts) == 1
    assert m.alerts[0].category == AlertCategory.EXECUTION_FAILURE


def test_success_execution_no_alert():
    m = PipelineMonitor()
    m.check_execution(_success_exec())
    assert len(m.alerts) == 0


def test_data_quality_missing_fraction_alert():
    m = PipelineMonitor()
    m.check_data_quality("node_a", "exec-001", row_count=100, missing_fraction=0.5)
    assert len(m.alerts) == 1
    assert m.alerts[0].category == AlertCategory.DATA_QUALITY


def test_data_quality_below_threshold_no_alert():
    m = PipelineMonitor()
    m.check_data_quality("node_a", "exec-001", row_count=100, missing_fraction=0.1)
    assert len(m.alerts) == 0


def test_data_quality_too_few_rows_alert():
    m = PipelineMonitor()
    m.check_data_quality("node_a", "exec-001", row_count=2, missing_fraction=0.0)
    assert any(a.category == AlertCategory.DATA_QUALITY for a in m.alerts)


def test_schema_change_alert():
    m = PipelineMonitor()
    m.check_schema_change(
        "node_a", "exec-001",
        reference_columns=("a", "b", "c"),
        current_columns=("a", "b", "d"),
    )
    assert len(m.alerts) == 1
    assert m.alerts[0].category == AlertCategory.SCHEMA_CHANGE


def test_no_schema_change_no_alert():
    m = PipelineMonitor()
    m.check_schema_change(
        "node_a", "exec-001",
        reference_columns=("a", "b"),
        current_columns=("a", "b"),
    )
    assert len(m.alerts) == 0


def test_data_drift_alert():
    m = PipelineMonitor()
    ref = {"col_a": {"mean": 1.0, "std": 0.1}}
    cur = {"col_a": {"mean": 2.0, "std": 0.1}}  # 100% drift
    m.check_data_drift("node_a", "exec-001", reference_stats=ref, current_stats=cur)
    assert len(m.alerts) > 0
    assert m.alerts[0].category == AlertCategory.DATA_DRIFT


def test_no_data_drift_no_alert():
    m = PipelineMonitor()
    ref = {"col_a": {"mean": 1.0}}
    cur = {"col_a": {"mean": 1.01}}  # tiny drift
    m.check_data_drift("node_a", "exec-001", reference_stats=ref, current_stats=cur)
    assert len(m.alerts) == 0


def test_model_degradation_alert_classification():
    m = PipelineMonitor()
    m.check_model_metrics("exec-001", "rf", "classification", {"accuracy": 0.30})
    assert any(a.category == AlertCategory.MODEL_DEGRADATION for a in m.alerts)


def test_model_no_alert_good_metrics():
    m = PipelineMonitor()
    m.check_model_metrics("exec-001", "rf", "classification", {"accuracy": 0.85})
    assert len(m.alerts) == 0


def test_alert_is_frozen():
    m = PipelineMonitor()
    m.check_execution(_failed_exec())
    alert = m.alerts[0]
    with pytest.raises((TypeError, AttributeError)):
        alert.severity = "INFO"


def test_drain_clears_alerts():
    m = PipelineMonitor()
    m.check_execution(_failed_exec())
    drained = m.drain()
    assert len(drained) == 1
    assert len(m.alerts) == 0


def test_alert_to_dict_serializable():
    m = PipelineMonitor()
    m.check_execution(_failed_exec())
    d = m.alerts[0].to_dict()
    json.dumps(d)
    assert "category" in d
    assert "severity" in d


def test_configurable_threshold():
    cfg = MonitoringConfig(max_missing_fraction=0.05)
    m = PipelineMonitor(config=cfg)
    m.check_data_quality("node_a", "exec-001", row_count=100, missing_fraction=0.10)
    assert len(m.alerts) == 1  # 10% > 5% threshold


def test_regression_r2_alert():
    m = PipelineMonitor()
    m.check_model_metrics("exec-001", "lr", "regression", {"r2": -0.5})
    assert any(a.category == AlertCategory.MODEL_DEGRADATION for a in m.alerts)
