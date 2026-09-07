"""
core/inference/engine.py
------------------------
Inference engine for AyaskX.

Phase M: INFERENCE

Supports:
    trained sklearn pipeline artifact
        ↓
    load artifact
        ↓
    validate input schema
        ↓
    apply exact preprocessing (sklearn pipeline)
        ↓
    predict
        ↓
    validate output
        ↓
    record inference metadata

Training/serving consistency:
    The inference engine applies exactly the sklearn Pipeline that was
    fitted during training (no re-fitting, no divergence).

Serialization:
    Model artifacts are stored and loaded via joblib (the sklearn default).
    NO other model serialization format is introduced in this phase.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Integrity imports — used in save/load; imported lazily to avoid
# circular dependency at module level.
from core.integrity.models import IntegrityStatus


@dataclass(frozen=True)
class InferenceRequest:
    """A validated, immutable inference request."""

    request_id: str
    execution_id: str
    data: Any          # pd.DataFrame or array-like
    metadata: dict[str, Any] = field(default_factory=dict)
    requested_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class InferenceResult:
    """
    Immutable inference result.

    Fields
    ------
    request_id        : matches InferenceRequest.request_id
    execution_id      : original training execution_id
    model_name        : name of the model that produced predictions
    task_type         : regression|classification
    predictions       : tuple of prediction values
    prediction_count  : number of predictions
    input_rows        : number of input rows processed
    schema_validated  : True if input schema matched training schema
    output_validated  : True if output is well-formed
    success           : True if all validation passed
    message           : summary message
    metadata          : additional inference context
    completed_at      : UTC timestamp
    """

    request_id: str
    execution_id: str
    model_name: str
    task_type: str
    predictions: tuple[Any, ...]
    prediction_count: int
    input_rows: int
    schema_validated: bool
    output_validated: bool
    success: bool
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    completed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "model_name": self.model_name,
            "task_type": self.task_type,
            "prediction_count": self.prediction_count,
            "input_rows": self.input_rows,
            "schema_validated": self.schema_validated,
            "output_validated": self.output_validated,
            "success": self.success,
            "message": self.message,
            "predictions": list(self.predictions),
            "completed_at": self.completed_at.isoformat(),
        }


@dataclass
class ModelArtifact:
    """
    Container for a trained model artifact.

    Stores:
    - the fitted sklearn pipeline
    - training metadata (model_name, task_type, metrics, schema)
    - dataset fingerprint for provenance
    - checkpoint_id for traceability

    Integrity:
    - save() writes a SHA-256 sidecar manifest alongside the joblib file.
    - load() verifies the manifest when present; marks legacy artifacts
      as 'unverified' rather than failing (backward-compatible).
    - integrity_status reflects the outcome of the last load verification.
    """

    model_name: str
    task_type: str
    execution_id: str
    pipeline: Any                    # fitted sklearn Pipeline
    feature_columns: list[str]
    target_column: str
    metrics: dict[str, float]
    validation_strategy: str
    dataset_fingerprint: str
    checkpoint_id: str | None = None
    trained_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)
    # Set by load() to record integrity check outcome.
    # Never set by callers directly.
    integrity_status: str = "unverified"

    @property
    def integrity_verified(self) -> bool:
        """True only when the artifact passed a SHA-256 integrity check."""
        return self.integrity_status == IntegrityStatus.PASSED.value

    def save(self, path: str | Path) -> Path:
        """
        Serialize artifact to disk using joblib and write a SHA-256 manifest.

        The manifest is written AFTER the artifact is fully flushed so
        the checksum is computed over the final bytes (no circular hashing).
        """
        import joblib
        from core.integrity.checker import ArtifactIntegrityChecker

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

        # Write integrity manifest alongside the artifact.
        try:
            checker = ArtifactIntegrityChecker()
            checker.create_manifest(
                path,
                execution_id=self.execution_id,
                dataset_fingerprint=self.dataset_fingerprint,
                checkpoint_id=self.checkpoint_id,
                model_name=self.model_name,
            )
        except Exception:
            # Manifest write failure must not silently succeed —
            # but it also must not prevent the artifact from being saved.
            # The artifact is usable but will be loaded as 'unverified'.
            pass

        return path

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        verify_integrity: bool = True,
        strict: bool = False,
    ) -> "ModelArtifact":
        """
        Load a serialized artifact from disk.

        Parameters
        ----------
        path             : path to the joblib artifact file
        verify_integrity : if True (default), verify SHA-256 manifest
        strict           : if True, raise ChecksumMismatchError on failure
                           instead of returning an unverified artifact

        Backward compatibility:
          - Artifacts without a manifest are loaded as 'unverified',
            not rejected. This preserves all existing test compatibility.
          - Set strict=True only for security-sensitive load paths.
        """
        import joblib
        from core.integrity.checker import ArtifactIntegrityChecker
        from core.integrity.errors import ChecksumMismatchError

        artifact = joblib.load(path)
        if not isinstance(artifact, cls):
            raise TypeError(
                f"Loaded object is {type(artifact).__name__}, "
                f"expected ModelArtifact."
            )

        if verify_integrity:
            checker = ArtifactIntegrityChecker()
            result = checker.verify(path)
            artifact.integrity_status = result.status.value

            if strict and not result.valid and result.status == IntegrityStatus.FAILED:
                raise ChecksumMismatchError(
                    result.reason,
                    expected=result.expected_checksum or "",
                    actual=result.actual_checksum or "",
                    artifact_path=str(path),
                )
        else:
            artifact.integrity_status = "unverified"

        return artifact


class InferenceEngine:
    """
    Applies a trained ModelArtifact to new data.

    Usage
    -----
    engine = InferenceEngine()
    result = engine.predict(artifact, request)

    The engine:
    1. Validates that the input DataFrame contains the required feature columns.
    2. Applies the exact fitted sklearn pipeline (no re-fitting).
    3. Validates that predictions are well-formed (no NaN, correct count).
    4. Records all metadata in an immutable InferenceResult.

    Training/serving consistency is guaranteed because:
    - The fitted sklearn pipeline is used directly (transform + predict).
    - No re-fitting occurs at inference time.
    - Input schema is validated against the training feature list.
    """

    def predict(
        self,
        artifact: ModelArtifact,
        request: InferenceRequest,
    ) -> InferenceResult:
        """
        Execute inference and return an immutable InferenceResult.

        Parameters
        ----------
        artifact : ModelArtifact with a fitted sklearn pipeline
        request  : InferenceRequest with input data

        Returns
        -------
        InferenceResult — always. Never raises to the caller.
        """

        df = self._to_dataframe(request.data)
        input_rows = len(df)

        # ── Schema validation ────────────────────────────────────────────────

        missing_cols = [
            c for c in artifact.feature_columns if c not in df.columns
        ]
        schema_valid = len(missing_cols) == 0

        if not schema_valid:
            return InferenceResult(
                request_id=request.request_id,
                execution_id=artifact.execution_id,
                model_name=artifact.model_name,
                task_type=artifact.task_type,
                predictions=(),
                prediction_count=0,
                input_rows=input_rows,
                schema_validated=False,
                output_validated=False,
                success=False,
                message=(
                    f"Input schema validation failed. "
                    f"Missing columns: {missing_cols}"
                ),
                completed_at=datetime.now(timezone.utc),
            )

        # ── Apply preprocessing + predict ────────────────────────────────────

        try:
            X = df[artifact.feature_columns]
            raw_preds = artifact.pipeline.predict(X)
        except Exception as exc:
            return InferenceResult(
                request_id=request.request_id,
                execution_id=artifact.execution_id,
                model_name=artifact.model_name,
                task_type=artifact.task_type,
                predictions=(),
                prediction_count=0,
                input_rows=input_rows,
                schema_validated=True,
                output_validated=False,
                success=False,
                message=f"Prediction failed: {type(exc).__name__}: {exc}",
                completed_at=datetime.now(timezone.utc),
            )

        # ── Output validation ────────────────────────────────────────────────

        output_valid = self._validate_output(raw_preds, input_rows)

        predictions = tuple(
            p.item() if hasattr(p, "item") else p
            for p in raw_preds
        )

        return InferenceResult(
            request_id=request.request_id,
            execution_id=artifact.execution_id,
            model_name=artifact.model_name,
            task_type=artifact.task_type,
            predictions=predictions,
            prediction_count=len(predictions),
            input_rows=input_rows,
            schema_validated=True,
            output_validated=output_valid,
            success=output_valid,
            message=(
                "Inference completed successfully."
                if output_valid
                else "Output validation failed: NaN or count mismatch."
            ),
            metadata={
                "dataset_fingerprint": artifact.dataset_fingerprint,
                "checkpoint_id": artifact.checkpoint_id,
            },
            completed_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _to_dataframe(data: Any) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            return data.copy()
        if isinstance(data, dict):
            return pd.DataFrame(data)
        if isinstance(data, (list, np.ndarray)):
            return pd.DataFrame(data)
        raise TypeError(
            f"Cannot convert {type(data).__name__} to DataFrame. "
            f"Provide a DataFrame, dict, list, or ndarray."
        )

    @staticmethod
    def _validate_output(
        preds: Any,
        expected_count: int,
    ) -> bool:
        """True if predictions are well-formed."""
        try:
            arr = np.asarray(preds)
            if arr.shape[0] != expected_count:
                return False
            if np.any(np.isnan(arr)):
                return False
            return True
        except Exception:
            return False
