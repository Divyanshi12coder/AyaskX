"""
tests/test_orchestrator.py
---------------------------
Integration tests for AyaskXOrchestrator — the coherent platform entry point.
Covers dataset adaptivity, multiple dataset types, end-to-end flow.
No existing tests modified.
"""

from __future__ import annotations
import uuid
import pytest
import numpy as np
import pandas as pd

from core.platform.orchestrator import AyaskXOrchestrator, OrchestratorResult


# ---------------------------------------------------------------------------
# Fixtures — small, synthetic datasets (no real files needed)
# ---------------------------------------------------------------------------


def _regression_df(n=100) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "feature_a": rng.normal(0, 1, n),
        "feature_b": rng.normal(5, 2, n),
        "feature_c": rng.integers(0, 10, n).astype(float),
        "target": rng.normal(10, 3, n),
    })


def _classification_df(n=120) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "age": rng.integers(18, 80, n).astype(float),
        "score": rng.normal(50, 15, n),
        "category": rng.choice(["A", "B", "C"], n),
        "label": rng.integers(0, 2, n),
    })


def _missing_values_df(n=80) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "x1": rng.normal(0, 1, n),
        "x2": rng.normal(0, 1, n),
        "target": rng.normal(5, 1, n),
    })
    # Inject ~20% missing in x2
    mask = rng.random(n) < 0.2
    df.loc[mask, "x2"] = float("nan")
    return df


def _categorical_df(n=100) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    return pd.DataFrame({
        "color": rng.choice(["red", "green", "blue", "yellow"], n),
        "size": rng.choice(["small", "medium", "large"], n),
        "weight": rng.normal(10, 2, n),
        "label": rng.integers(0, 2, n),
    })


def _temporal_df(n=100) -> pd.DataFrame:
    rng = np.random.default_rng(9)
    import pandas as pd
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": dates,
        "value_a": rng.normal(0, 1, n),
        "value_b": rng.normal(5, 2, n),
        "target": rng.normal(10, 1, n),
    })


def _grouped_df(n=100) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    groups = rng.choice(["G1", "G2", "G3"], n)
    return pd.DataFrame({
        "mine_id": groups,
        "feature_a": rng.normal(0, 1, n),
        "feature_b": rng.normal(5, 2, n),
        "target": rng.normal(10, 1, n),
    })


def _spatial_df(n=100) -> pd.DataFrame:
    rng = np.random.default_rng(13)
    return pd.DataFrame({
        "lat": rng.uniform(-90, 90, n),
        "lon": rng.uniform(-180, 180, n),
        "altitude": rng.normal(500, 100, n),
        "target": rng.integers(0, 2, n),
    })


def _leakage_df(n=80) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    target = rng.integers(0, 2, n)
    return pd.DataFrame({
        "feature_a": rng.normal(0, 1, n),
        "future_value": rng.normal(0, 1, n),   # leakage hint
        "actual_outcome": target.astype(float), # leakage hint
        "target": target,
    })


# ---------------------------------------------------------------------------
# ORCHESTRATOR INSTANCE
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def orch(tmp_path_factory):
    root = tmp_path_factory.mktemp("ckpts")
    arts = tmp_path_factory.mktemp("arts")
    return AyaskXOrchestrator(checkpoint_root=root, artifact_root=arts)


# ---------------------------------------------------------------------------
# BASIC FLOW
# ---------------------------------------------------------------------------


def test_orchestrator_runs_regression(orch):
    result = orch.run(_regression_df(), dataset_path="test/regression.csv",
                      target="target", task_type="regression")
    assert isinstance(result, OrchestratorResult)
    assert result.execution_id
    assert result.success is True


def test_orchestrator_runs_classification(orch):
    result = orch.run(_classification_df(), dataset_path="test/clf.csv",
                      target="label", task_type="classification")
    assert result.success is True
    assert result.training_result is not None


def test_result_is_frozen(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    with pytest.raises((TypeError, AttributeError)):
        result.success = False


def test_result_has_execution_id(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert result.execution_id
    assert len(result.execution_id) > 0


def test_result_has_fingerprint(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert result.dataset_fingerprint.startswith("sha:")


def test_to_summary_is_serializable(orch):
    import json
    result = orch.run(_regression_df(), target="target", task_type="regression")
    summary = result.to_summary()
    json.dumps(summary)
    assert "best_model" in summary


# ---------------------------------------------------------------------------
# DATASET ADAPTIVITY
# ---------------------------------------------------------------------------


def test_missing_values_handled(orch):
    result = orch.run(_missing_values_df(), target="target", task_type="regression")
    assert result.success is True


def test_categorical_dataset_handled(orch):
    result = orch.run(_categorical_df(), target="label", task_type="classification")
    assert result.success is True


def test_temporal_dataset_handled(orch):
    result = orch.run(_temporal_df(), target="target", task_type="regression")
    assert isinstance(result, OrchestratorResult)
    # May succeed or produce structured failure, must not crash


def test_grouped_dataset_handled(orch):
    result = orch.run(_grouped_df(), target="target", task_type="regression")
    assert isinstance(result, OrchestratorResult)


def test_spatial_dataset_handled(orch):
    result = orch.run(_spatial_df(), target="target", task_type="classification")
    assert isinstance(result, OrchestratorResult)


def test_leakage_detected_in_result(orch):
    result = orch.run(_leakage_df(), target="target", task_type="classification")
    assert result.leakage_report is not None
    # Risky features must have been detected
    assert len(result.leakage_report.risky_features) > 0


def test_leakage_warning_in_result(orch):
    result = orch.run(_leakage_df(), target="target", task_type="classification")
    assert any("eakage" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# STAGE OUTPUTS
# ---------------------------------------------------------------------------


def test_characterization_present(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert result.characterization is not None
    assert result.characterization.rows > 0


def test_task_detection_present(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert result.task_detection is not None


def test_validation_strategy_present(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert result.validation_strategy is not None


def test_candidate_report_present(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert result.candidate_report is not None
    assert len(result.candidate_report.candidates) > 0


def test_best_model_is_set(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert result.training_result.best_model_name is not None


def test_best_score_is_numeric(orch):
    result = orch.run(_regression_df(), target="target", task_type="regression")
    assert isinstance(result.training_result.best_score, float)


# ---------------------------------------------------------------------------
# INFERENCE AFTER TRAINING
# ---------------------------------------------------------------------------


def test_inference_after_training(orch):
    df = _classification_df()
    result = orch.run(df, target="label", task_type="classification")
    if result.model_artifact and result.model_artifact.pipeline is not None:
        inf_data = df.drop(columns=["label"]).head(5)
        inf_result = orch.predict(result.model_artifact, inf_data)
        assert inf_result.success is True
        assert inf_result.prediction_count == 5


# ---------------------------------------------------------------------------
# SELF-HEALING INTEGRATION
# ---------------------------------------------------------------------------


def test_analyze_and_heal_on_failed_execution(orch):
    from datetime import datetime, timezone
    from core.pipeline.executor import NodeExecution, PipelineExecution
    from core.pipeline.status import NodeStatus, PipelineStatus

    now = datetime.now(timezone.utc)
    node = NodeExecution(
        execution_id="exec-heal", node_id="failing_node",
        status=NodeStatus.FAILED, started_at=now, finished_at=now,
        error_type="RuntimeError", error_message="injected failure",
    )
    exec_ = PipelineExecution(
        execution_id="exec-heal", status=PipelineStatus.FAILED,
        nodes=(node,), started_at=now, finished_at=now,
    )
    outcome = orch.analyze_and_heal(exec_)
    assert "fault" in outcome
    assert "root_cause" in outcome
    assert "repair_plan" in outcome
    assert "recovery_result" in outcome


# ---------------------------------------------------------------------------
# ERROR HANDLING
# ---------------------------------------------------------------------------


def test_empty_dataframe_produces_result_not_crash(orch):
    """Empty DataFrame should produce a safe failed result, not raise."""
    df = pd.DataFrame({"a": [], "target": []})
    result = orch.run(df, target="target", task_type="regression")
    assert isinstance(result, OrchestratorResult)
    assert result.success is False


def test_missing_target_column_produces_safe_failure(orch):
    """Specifying a target not in columns should produce a structured failure."""
    df = _regression_df()
    result = orch.run(df, target="nonexistent_column", task_type="regression")
    assert result.success is False
