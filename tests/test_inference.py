"""
tests/test_inference.py
------------------------
Tests for InferenceEngine and ModelArtifact.
No existing tests modified.
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from core.inference.engine import InferenceEngine, InferenceRequest, InferenceResult, ModelArtifact


_NOW = datetime.now(timezone.utc)


def _simple_clf_pipeline() -> Pipeline:
    """A fitted binary classification pipeline."""
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0],
                      "b": [0.1, 0.2, 0.3, 0.4, 0.5]})
    y = [0, 1, 0, 1, 0]
    p = Pipeline([("scaler", StandardScaler()), ("model", RandomForestClassifier(n_estimators=5, random_state=42))])
    p.fit(X, y)
    return p


def _simple_reg_pipeline() -> Pipeline:
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0],
                      "b": [0.1, 0.2, 0.3, 0.4, 0.5]})
    y = [1.0, 2.0, 3.0, 4.0, 5.0]
    p = Pipeline([("scaler", StandardScaler()), ("model", RandomForestRegressor(n_estimators=5, random_state=42))])
    p.fit(X, y)
    return p


def _artifact(task="classification") -> ModelArtifact:
    pipeline = _simple_clf_pipeline() if task == "classification" else _simple_reg_pipeline()
    return ModelArtifact(
        model_name="test_model",
        task_type=task,
        execution_id="exec-001",
        pipeline=pipeline,
        feature_columns=["a", "b"],
        target_column="y",
        metrics={"accuracy": 0.8},
        validation_strategy="random_holdout",
        dataset_fingerprint="sha:5x2:abc123",
        checkpoint_id="ckpt-001",
    )


def _request(data: pd.DataFrame | None = None) -> InferenceRequest:
    if data is None:
        data = pd.DataFrame({"a": [1.0, 2.0], "b": [0.1, 0.2]})
    return InferenceRequest(
        request_id=str(uuid.uuid4()),
        execution_id="exec-001",
        data=data,
    )


engine = InferenceEngine()


# ---------------------------------------------------------------------------
# SUCCESS PATH
# ---------------------------------------------------------------------------

def test_inference_success():
    artifact = _artifact()
    result = engine.predict(artifact, _request())
    assert result.success is True
    assert result.prediction_count == 2


def test_inference_result_is_frozen():
    result = engine.predict(_artifact(), _request())
    with pytest.raises((TypeError, AttributeError)):
        result.success = False


def test_inference_schema_validated():
    result = engine.predict(_artifact(), _request())
    assert result.schema_validated is True


def test_inference_output_validated():
    result = engine.predict(_artifact(), _request())
    assert result.output_validated is True


def test_predictions_count_matches_input_rows():
    data = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [0.1, 0.2, 0.3]})
    result = engine.predict(_artifact(), _request(data))
    assert result.prediction_count == 3


def test_regression_inference():
    artifact = _artifact("regression")
    result = engine.predict(artifact, _request())
    assert result.success is True
    assert result.task_type == "regression"


# ---------------------------------------------------------------------------
# SCHEMA FAILURE
# ---------------------------------------------------------------------------

def test_missing_column_fails_schema_validation():
    bad_data = pd.DataFrame({"a": [1.0]})  # missing "b"
    result = engine.predict(_artifact(), _request(bad_data))
    assert result.schema_validated is False
    assert result.success is False


def test_missing_column_produces_zero_predictions():
    bad_data = pd.DataFrame({"a": [1.0]})
    result = engine.predict(_artifact(), _request(bad_data))
    assert result.prediction_count == 0


# ---------------------------------------------------------------------------
# SERIALIZATION
# ---------------------------------------------------------------------------

def test_to_dict_is_serializable():
    result = engine.predict(_artifact(), _request())
    d = result.to_dict()
    json.dumps(d)
    assert "predictions" in d


def test_execution_id_in_result():
    result = engine.predict(_artifact(), _request())
    assert result.execution_id == "exec-001"


def test_model_name_in_result():
    result = engine.predict(_artifact(), _request())
    assert result.model_name == "test_model"


# ---------------------------------------------------------------------------
# ARTIFACT METADATA
# ---------------------------------------------------------------------------

def test_artifact_fingerprint_preserved():
    artifact = _artifact()
    assert artifact.dataset_fingerprint == "sha:5x2:abc123"


def test_artifact_checkpoint_preserved():
    artifact = _artifact()
    assert artifact.checkpoint_id == "ckpt-001"


# ---------------------------------------------------------------------------
# MODEL ARTIFACT SAVE/LOAD
# ---------------------------------------------------------------------------

def test_artifact_save_load_roundtrip(tmp_path):
    artifact = _artifact()
    path = tmp_path / "test_model.joblib"
    artifact.save(path)
    loaded = ModelArtifact.load(path)
    assert loaded.model_name == artifact.model_name
    assert loaded.task_type == artifact.task_type
    assert loaded.feature_columns == artifact.feature_columns


def test_loaded_artifact_can_predict(tmp_path):
    artifact = _artifact()
    path = tmp_path / "test_model.joblib"
    artifact.save(path)
    loaded = ModelArtifact.load(path)
    result = engine.predict(loaded, _request())
    assert result.success is True
