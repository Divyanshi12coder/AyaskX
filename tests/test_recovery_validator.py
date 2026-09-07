"""
tests/test_recovery_validator.py
---------------------------------
Tests for RecoveryValidator — structural validation gate.

No existing tests are modified.
"""

from __future__ import annotations

import tempfile
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.recovery.validator import RecoveryValidator
from core.recovery.models import ValidationResult, ValidationCheck
from core.pipeline.executor import NodeExecution
from core.pipeline.status import NodeStatus


_NOW = datetime.now(timezone.utc)
validator = RecoveryValidator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_exec(
    node_id: str = "node_a",
    *,
    status: NodeStatus = NodeStatus.SUCCESS,
    error_type: str | None = None,
    error_message: str | None = None,
    output_metadata: dict | None = None,
    checkpoint_id: str | None = "ckpt-001",
) -> NodeExecution:
    return NodeExecution(
        execution_id="exec-001",
        node_id=node_id,
        status=status,
        started_at=_NOW,
        finished_at=_NOW,
        error_type=error_type,
        error_message=error_message,
        output_metadata=output_metadata if output_metadata is not None else {"result_type": "int"},
        checkpoint_id=checkpoint_id,
    )


@dataclass(frozen=True)
class _FakeCheckpoint:
    checkpoint_id: str = "ckpt-001"
    node_id: str = "node_a"
    execution_id: str = "exec-001"
    validation_status: str = "passed"
    data_hash: str = "abc123"
    artifact_path: str | None = None


# ---------------------------------------------------------------------------
# NODE EXECUTION VALIDATION
# ---------------------------------------------------------------------------


def test_valid_success_node_passes():
    node = _node_exec(status=NodeStatus.SUCCESS, output_metadata={"result_type": "int"})
    result = validator.validate_node_execution(node)
    assert result.passed is True


def test_failed_node_fails_validation():
    node = _node_exec(
        status=NodeStatus.FAILED,
        error_type="RuntimeError",
        error_message="something broke",
        output_metadata={},
    )
    result = validator.validate_node_execution(node)
    assert result.passed is False


def test_failed_node_has_status_check_failure():
    node = _node_exec(status=NodeStatus.FAILED, output_metadata={})
    result = validator.validate_node_execution(node)
    assert "node_status_success" in result.failures


def test_empty_output_metadata_fails():
    node = _node_exec(status=NodeStatus.SUCCESS, output_metadata={})
    result = validator.validate_node_execution(node)
    assert result.passed is False
    assert "output_metadata_present" in result.failures


def test_schema_columns_match_passes():
    node = _node_exec(
        status=NodeStatus.SUCCESS,
        output_metadata={"result_type": "DataFrame", "columns": ["a", "b", "c"]},
    )
    result = validator.validate_node_execution(node, expected_columns=["a", "b"])
    assert result.passed is True


def test_schema_columns_mismatch_fails():
    node = _node_exec(
        status=NodeStatus.SUCCESS,
        output_metadata={"result_type": "DataFrame", "columns": ["a", "b"]},
    )
    result = validator.validate_node_execution(node, expected_columns=["a", "b", "missing_col"])
    assert result.passed is False
    assert "schema_columns_match" in result.failures


def test_missing_columns_key_fails_schema_check():
    node = _node_exec(
        status=NodeStatus.SUCCESS,
        output_metadata={"result_type": "DataFrame"},
    )
    result = validator.validate_node_execution(node, expected_columns=["a"])
    assert "schema_columns_match" in result.failures


def test_validation_result_is_immutable():
    node = _node_exec()
    result = validator.validate_node_execution(node)
    with pytest.raises((TypeError, AttributeError)):
        result.passed = False  # type: ignore[misc]


def test_validation_checks_are_tuples():
    node = _node_exec()
    result = validator.validate_node_execution(node)
    assert isinstance(result.checks, tuple)
    assert isinstance(result.failures, tuple)


# ---------------------------------------------------------------------------
# CHECKPOINT VALIDATION
# ---------------------------------------------------------------------------


def test_valid_checkpoint_passes():
    ckpt = _FakeCheckpoint()
    result = validator.validate_checkpoint(ckpt)
    assert result.passed is True


def test_checkpoint_with_invalid_status_fails():
    ckpt = _FakeCheckpoint(validation_status="failed")
    result = validator.validate_checkpoint(ckpt)
    assert result.passed is False
    assert "validation_status_passed" in result.failures


def test_checkpoint_with_missing_hash_fails():
    ckpt = _FakeCheckpoint(data_hash="")
    result = validator.validate_checkpoint(ckpt)
    assert result.passed is False
    assert "data_hash_present" in result.failures


def test_checkpoint_with_nonexistent_artifact_path_fails():
    ckpt = _FakeCheckpoint(artifact_path="/nonexistent/path/artifact.json")
    result = validator.validate_checkpoint(ckpt)
    assert result.passed is False
    assert "artifact_path_exists" in result.failures


def test_checkpoint_with_existing_artifact_path_passes():
    with tempfile.NamedTemporaryFile(
        suffix=".json", mode="w", delete=False
    ) as f:
        json.dump({"data": 1}, f)
        tmp_path = f.name

    try:
        ckpt = _FakeCheckpoint(artifact_path=tmp_path)
        result = validator.validate_checkpoint(ckpt)
        assert result.passed is True
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_checkpoint_no_artifact_path_passes():
    """In-memory checkpoint with artifact_path=None should pass."""
    ckpt = _FakeCheckpoint(artifact_path=None)
    result = validator.validate_checkpoint(ckpt)
    assert result.passed is True


# ---------------------------------------------------------------------------
# FULL VALIDATION (node + checkpoint combined)
# ---------------------------------------------------------------------------


def test_full_validation_success():
    node = _node_exec()
    ckpt = _FakeCheckpoint()
    result = validator.validate_full(node, ckpt)
    assert result.passed is True


def test_full_validation_fails_when_node_fails():
    node = _node_exec(status=NodeStatus.FAILED, output_metadata={})
    ckpt = _FakeCheckpoint()
    result = validator.validate_full(node, ckpt)
    assert result.passed is False


def test_full_validation_fails_when_checkpoint_invalid():
    node = _node_exec()
    ckpt = _FakeCheckpoint(validation_status="unknown")
    result = validator.validate_full(node, ckpt)
    assert result.passed is False


def test_full_validation_without_checkpoint():
    node = _node_exec()
    result = validator.validate_full(node, checkpoint=None)
    assert result.passed is True


# ---------------------------------------------------------------------------
# RESULT STRUCTURE
# ---------------------------------------------------------------------------


def test_validation_result_has_message():
    node = _node_exec(status=NodeStatus.FAILED, output_metadata={})
    result = validator.validate_node_execution(node)
    assert result.message
    assert len(result.message) > 0


def test_passing_validation_has_empty_failures():
    node = _node_exec()
    result = validator.validate_node_execution(node)
    assert result.failures == ()


def test_to_dict_is_serializable():
    node = _node_exec()
    result = validator.validate_node_execution(node)
    d = result.to_dict()
    import json
    json.dumps(d)  # must not raise
    assert "passed" in d
    assert "checks" in d
    assert "failures" in d
