"""
api/services/dataset_service.py
---------------------------------
Thin adapter between the API layer and AyaskX frozen core dataset modules.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from api.exceptions import UnsupportedFileTypeError, UploadTooLargeError, ValidationError

_ALLOWED_EXTENSIONS = {".csv", ".parquet", ".tsv"}
_MAX_FILENAME_LEN = 128


def _safe_filename(filename: str) -> str:
    """Return a safe filename: stem only, alphanumeric/underscore/dash."""
    import re
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower()
    safe_stem = re.sub(r"[^\w\-]", "_", stem)[:_MAX_FILENAME_LEN]
    return safe_stem + ext


def _df_fingerprint(df: pd.DataFrame) -> str:
    try:
        return hashlib.sha256(
            pd.util.hash_pandas_object(df, index=False).values.tobytes()
        ).hexdigest()[:16]
    except Exception:
        return "nohash"


class DatasetService:
    def __init__(
        self,
        dataset_store,
        upload_tmp_root: Path,
        max_upload_bytes: int,
    ) -> None:
        self._store = dataset_store
        self._upload_tmp = upload_tmp_root
        self._max_bytes = max_upload_bytes

    # -----------------------------------------------------------------------
    # Upload
    # -----------------------------------------------------------------------

    def upload(
        self,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:
        ext = Path(filename).suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(filename)
        if len(content) > self._max_bytes:
            raise UploadTooLargeError(self._max_bytes // (1024 * 1024))

        safe_name = _safe_filename(filename)
        dataset_id = str(uuid.uuid4())
        dest = self._upload_tmp / f"{dataset_id}_{safe_name}"
        dest.write_bytes(content)

        # Read to get basic metadata (no full profile here — that's separate)
        try:
            df = self._load_df(dest, ext)
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise ValidationError(
                f"Dataset could not be parsed as {ext.lstrip('.') or 'the declared format'}."
            ) from exc
        fingerprint = _df_fingerprint(df)

        registered_at = datetime.now(timezone.utc).isoformat()
        record = {
            "dataset_id": dataset_id,
            "original_filename": filename,
            "safe_filename": safe_name,
            "file_path": str(dest),
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
            "dtypes": {c: str(t) for c, t in df.dtypes.items()},
            "fingerprint": fingerprint,
            "size_bytes": len(content),
            # Compatibility aliases used by the typed frontend contract.
            "file_size_bytes": len(content),
            "registered_at": registered_at,
            "uploaded_at": registered_at,
        }
        self._store.save(dataset_id, record)
        return record

    # -----------------------------------------------------------------------
    # Retrieval
    # -----------------------------------------------------------------------

    def get_metadata(self, dataset_id: str) -> dict[str, Any] | None:
        return self._store.get(dataset_id)

    def list_datasets(self) -> list[dict[str, Any]]:
        return self._store.list_all()

    # -----------------------------------------------------------------------
    # Profile
    # -----------------------------------------------------------------------

    def get_profile(self, dataset_id: str, target: str | None = None) -> dict[str, Any]:
        record = self._store.get(dataset_id)
        if not record:
            return {}
        df = self._load_df_from_record(record)
        from core.datasets.characterization.characterizer import DatasetCharacterizer
        char = DatasetCharacterizer().characterize(df, record["original_filename"])
        from core.task_detection.detector import TaskDetector

        detected = TaskDetector().detect(df)
        selected_target = target or detected.target
        if selected_target is not None and selected_target not in df.columns:
            raise ValueError(f"Target column '{selected_target}' does not exist in this dataset")

        profile = char.to_dict() if hasattr(char, "to_dict") else vars(char)
        profile.update({
            "target": selected_target,
            "task_type": detected.task_type,
            "task_confidence": detected.confidence,
            "task_warnings": list(detected.warnings),
            "task_candidates": [
                {"column": candidate.column, "score": candidate.score, "reason": candidate.reason}
                for candidate in detected.candidates
            ],
        })
        return profile

    # -----------------------------------------------------------------------
    # Feature roles
    # -----------------------------------------------------------------------

    def get_feature_roles(self, dataset_id: str, target: str | None = None) -> dict[str, Any]:
        record = self._store.get(dataset_id)
        if not record:
            return {}
        df = self._load_df_from_record(record)
        from core.datasets.characterization.characterizer import DatasetCharacterizer
        from core.feature_roles.detector import FeatureRoleDetector
        if target is not None and target not in df.columns:
            raise ValueError(f"Target column '{target}' does not exist in this dataset")
        report = FeatureRoleDetector().detect(df, target=target)
        return report.to_dict() if hasattr(report, "to_dict") else vars(report)

    # -----------------------------------------------------------------------
    # Leakage
    # -----------------------------------------------------------------------

    def get_leakage(self, dataset_id: str, target: str | None = None) -> dict[str, Any]:
        record = self._store.get(dataset_id)
        if not record:
            return {}
        df = self._load_df_from_record(record)
        from core.leakage.detector import LeakageDetector
        if target is not None and target not in df.columns:
            raise ValueError(f"Target column '{target}' does not exist in this dataset")
        report = LeakageDetector().analyze(df, target=target)
        return report.to_dict() if hasattr(report, "to_dict") else vars(report)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _load_df(self, path: Path, ext: str) -> pd.DataFrame:
        if ext == ".csv":
            return pd.read_csv(path)
        elif ext == ".tsv":
            return pd.read_csv(path, sep="\t")
        elif ext == ".parquet":
            return pd.read_parquet(path)
        raise UnsupportedFileTypeError(path.name)

    def _load_df_from_record(self, record: dict[str, Any]) -> pd.DataFrame:
        path = Path(record["file_path"])
        ext = Path(record["safe_filename"]).suffix.lower()
        return self._load_df(path, ext)
