from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)


@dataclass(frozen=True)
class ColumnCharacterization:
    name: str
    dtype: str
    semantic_role: str
    missing_count: int
    missing_fraction: float
    unique_count: int
    unique_fraction: float
    mean: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "semantic_role": self.semantic_role,
            "missing_count": self.missing_count,
            "missing_pct": self.missing_fraction,
            "unique_count": self.unique_count,
            "unique_fraction": self.unique_fraction,
            "mean": self.mean,
            "std": self.std,
            "min": self.minimum,
            "max": self.maximum,
        }


@dataclass(frozen=True)
class DatasetCharacterization:
    path: str
    rows: int
    columns: int
    column_count: int

    numeric_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    datetime_columns: tuple[str, ...]

    spatial_columns: tuple[str, ...]
    temporal_columns: tuple[str, ...]
    group_columns: tuple[str, ...]
    identifier_columns: tuple[str, ...]
    target_candidates: tuple[str, ...]

    high_cardinality_columns: tuple[str, ...]
    constant_columns: tuple[str, ...]
    missing_columns: tuple[str, ...]

    column_profiles: tuple[ColumnCharacterization, ...]

    dataset_role: str
    duplicate_rows: int = 0

    def to_dict(self) -> dict[str, object]:
        """Stable API-friendly representation of observed dataset facts."""
        return {
            "path": self.path,
            "rows": self.rows,
            "columns": self.columns,
            # Frontend/API aliases retained alongside the core naming.
            "n_rows": self.rows,
            "n_cols": self.columns,
            "column_count": self.column_count,
            "numeric_columns": list(self.numeric_columns),
            "categorical_columns": list(self.categorical_columns),
            "datetime_columns": list(self.datetime_columns),
            "spatial_columns": list(self.spatial_columns),
            "temporal_columns": list(self.temporal_columns),
            "group_columns": list(self.group_columns),
            "identifier_columns": list(self.identifier_columns),
            "target_candidates": list(self.target_candidates),
            "high_cardinality_columns": list(self.high_cardinality_columns),
            "constant_columns": list(self.constant_columns),
            "missing_columns": list(self.missing_columns),
            "missing_total": sum(p.missing_count for p in self.column_profiles),
            "duplicate_rows": self.duplicate_rows,
            "columns_profile": [p.to_dict() for p in self.column_profiles],
            # Existing UI contract uses this name.
            "columns": [p.to_dict() for p in self.column_profiles],
            "dataset_role": self.dataset_role,
        }


class DatasetCharacterizer:
    """
    Dataset characterization layer for AyaskX.

    Responsibilities:
        - Inspect dataframe structure
        - Detect physical data types
        - Detect semantic roles
        - Detect spatial/temporal/group columns
        - Identify possible target columns
        - Identify basic data-quality signals
        - Classify the broad dataset role

    This component DOES NOT:
        - select a model
        - train a model
        - select the final target
        - modify the dataframe
    """

    LATITUDE_NAMES = {
        "latitude",
        "lat",
        "lat_deg",
        "latitude_deg",
        "lat_dd",
    }

    LONGITUDE_NAMES = {
        "longitude",
        "lon",
        "lng",
        "long",
        "lon_deg",
        "longitude_deg",
        "longitude_dd",
    }

    TIME_KEYWORDS = (
        "time",
        "date",
        "datetime",
        "timestamp",
        "year",
        "month",
        "day",
    )

    GROUP_NAMES = {
        "mine_id",
        "mineid",
        "site_id",
        "siteid",
        "block_id",
        "blockid",
        "machine_id",
        "machineid",
        "equipment_id",
        "equipmentid",
        "borehole_id",
        "boreholeid",
        "sample_id",
        "sampleid",
    }

    TARGET_KEYWORDS = (
        "target",
        "label",
        "class",
        "grade",
        "production",
        "output",
        "yield",
        "prospectivity",
        "shortfall",
        "failure",
        "recovery",
    )

    METADATA_KEYWORDS = (
        "description",
        "purpose",
        "limitation",
        "generator",
        "real_or_synthetic",
        "source",
        "feature",
        "data_type",
        "target_or_feature",
        "leakage_risk",
    )

    REPORT_KEYWORDS = (
        "report",
        "warning",
        "error",
        "violation",
    )

    def characterize(
        self,
        df: pd.DataFrame,
        path: str | Path = "",
    ) -> DatasetCharacterization:

        if not isinstance(df, pd.DataFrame):
            raise TypeError(
                "df must be a pandas DataFrame."
            )

        if df.empty:
            raise ValueError(
                "Cannot characterize an empty dataset."
            )

        numeric_columns = []
        categorical_columns = []
        datetime_columns = []

        spatial_columns = []
        temporal_columns = []
        group_columns = []
        identifier_columns = []
        target_candidates = []

        high_cardinality_columns = []
        constant_columns = []
        missing_columns = []

        column_profiles = []

        for column in df.columns:

            name = str(column)
            series = df[column]

            dtype = str(series.dtype)

            numeric_stats: dict[str, float | None] = {
                "mean": None, "std": None, "minimum": None, "maximum": None,
            }
            if is_numeric_dtype(series) and not is_bool_dtype(series):
                numeric = pd.to_numeric(series, errors="coerce")
                numeric_stats = {
                    "mean": _finite_float(numeric.mean()),
                    "std": _finite_float(numeric.std()),
                    "minimum": _finite_float(numeric.min()),
                    "maximum": _finite_float(numeric.max()),
                }

            missing_count = int(
                series.isna().sum()
            )

            missing_fraction = (
                missing_count / len(df)
            )

            unique_count = int(
                series.nunique(
                    dropna=True
                )
            )

            unique_fraction = (
                unique_count / len(df)
            )

            normalized = self._normalize(
                name
            )

            semantic_role = (
                self._infer_semantic_role(
                    name=name,
                    normalized=normalized,
                    series=series,
                    unique_count=unique_count,
                    unique_fraction=unique_fraction,
                )
            )

            # --------------------------------------------------
            # Physical dtype classification
            # --------------------------------------------------

            if is_datetime64_any_dtype(series):

                datetime_columns.append(name)

            elif (
                is_numeric_dtype(series)
                and not is_bool_dtype(series)
            ):

                numeric_columns.append(name)

            else:

                categorical_columns.append(name)

            # --------------------------------------------------
            # Semantic classification
            # --------------------------------------------------

            if semantic_role == "spatial":

                spatial_columns.append(name)

            elif semantic_role == "temporal":

                temporal_columns.append(name)

                if name not in datetime_columns:
                    datetime_columns.append(name)

            elif semantic_role == "group":

                group_columns.append(name)

            elif semantic_role == "identifier":

                identifier_columns.append(name)

            elif semantic_role == "target_candidate":

                target_candidates.append(name)

            # --------------------------------------------------
            # Quality signals
            # --------------------------------------------------

            if missing_count > 0:

                missing_columns.append(name)

            if unique_count <= 1:

                constant_columns.append(name)

            elif (
                unique_fraction >= 0.90
                and len(df) >= 10
            ):

                high_cardinality_columns.append(
                    name
                )

            column_profiles.append(
                ColumnCharacterization(
                    name=name,
                    dtype=dtype,
                    semantic_role=semantic_role,
                    missing_count=missing_count,
                    missing_fraction=float(
                        missing_fraction
                    ),
                    unique_count=unique_count,
                    unique_fraction=float(
                        unique_fraction
                    ),
                    **numeric_stats,
                )
            )

        dataset_role = self._infer_dataset_role(
            path=Path(path),
            target_candidates=target_candidates,
            spatial_columns=spatial_columns,
            temporal_columns=temporal_columns,
        )

        return DatasetCharacterization(
            path=str(path),
            rows=len(df),
            columns=len(df.columns),
            column_count=len(df.columns),

            numeric_columns=tuple(
                numeric_columns
            ),

            categorical_columns=tuple(
                categorical_columns
            ),

            datetime_columns=tuple(
                dict.fromkeys(
                    datetime_columns
                )
            ),

            spatial_columns=tuple(
                spatial_columns
            ),

            temporal_columns=tuple(
                temporal_columns
            ),

            group_columns=tuple(
                group_columns
            ),

            identifier_columns=tuple(
                identifier_columns
            ),

            target_candidates=tuple(
                target_candidates
            ),

            high_cardinality_columns=tuple(
                high_cardinality_columns
            ),

            constant_columns=tuple(
                constant_columns
            ),

            missing_columns=tuple(
                missing_columns
            ),

            column_profiles=tuple(
                column_profiles
            ),

            dataset_role=dataset_role,
            duplicate_rows=int(df.duplicated().sum()),
        )

    # ==========================================================
    # SEMANTIC ROLE DETECTION
    # ==========================================================

    def _infer_semantic_role(
        self,
        name: str,
        normalized: str,
        series: pd.Series,
        unique_count: int,
        unique_fraction: float,
    ) -> str:

        # ------------------------------------------------------
        # Spatial
        # ------------------------------------------------------

        if (
            normalized in self.LATITUDE_NAMES
            or normalized in self.LONGITUDE_NAMES
            or "latitude" in normalized
            or "longitude" in normalized
        ):

            return "spatial"

        # ------------------------------------------------------
        # Native datetime
        # ------------------------------------------------------

        if is_datetime64_any_dtype(series):

            return "temporal"

        # ------------------------------------------------------
        # Date/time represented as strings
        # ------------------------------------------------------

        if any(
            keyword in normalized
            for keyword in self.TIME_KEYWORDS
        ):

            parsed = self._safe_datetime_parse(
                series
            )

            if parsed is not None:

                valid_fraction = float(
                    parsed.notna().mean()
                )

                if valid_fraction >= 0.80:

                    return "temporal"

        # ------------------------------------------------------
        # Group/entity
        # ------------------------------------------------------

        if normalized in self.GROUP_NAMES:

            return "group"

        # Generic *_id detection
        if (
            normalized.endswith("_id")
            or normalized.endswith("id")
        ):

            if unique_fraction < 0.90:

                return "group"

            return "identifier"

        # ------------------------------------------------------
        # Metadata
        # ------------------------------------------------------

        if any(
            keyword in normalized
            for keyword in self.METADATA_KEYWORDS
        ):

            return "metadata"

        # ------------------------------------------------------
        # Target candidate
        # ------------------------------------------------------

        if any(
            keyword in normalized
            for keyword in self.TARGET_KEYWORDS
        ):

            return "target_candidate"

        # ------------------------------------------------------
        # High-cardinality textual field
        # ------------------------------------------------------

        if (
            not is_numeric_dtype(series)
            and unique_fraction >= 0.90
        ):

            return "identifier"

        # ------------------------------------------------------
        # Normal categorical feature
        # ------------------------------------------------------

        if (
            not is_numeric_dtype(series)
            and unique_count
            <= max(
                20,
                int(len(series) * 0.10),
            )
        ):

            return "categorical"

        return "feature"

    # ==========================================================
    # DATASET ROLE DETECTION
    # ==========================================================

    def _infer_dataset_role(
        self,
        path: Path,
        target_candidates: list[str],
        spatial_columns: list[str],
        temporal_columns: list[str],
    ) -> str:

        path_text = str(path).lower()

        # Reports must never automatically become
        # training datasets.
        if any(
            keyword in path_text
            for keyword in self.REPORT_KEYWORDS
        ):

            return "report"

        # Metadata files are supporting information.
        if "metadata" in path_text:

            return "metadata"

        # Explicit ML-ready datasets.
        if "ml_ready" in path_text:

            return "ml_ready"

        # Scenario datasets.
        if "scenario" in path_text:

            return "scenario"

        # Synthetic source datasets.
        if "synthetic" in path_text:

            return "source_data"

        # Generic fallback.
        if spatial_columns:

            return "spatial_dataset"

        if target_candidates:

            return "potential_ml_dataset"

        if temporal_columns:

            return "temporal_dataset"

        return "tabular_dataset"

    # ==========================================================
    # HELPERS
    # ==========================================================

    @staticmethod
    def _normalize(name: str) -> str:

        return (
            str(name)
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

    @staticmethod
    def _safe_datetime_parse(
        series: pd.Series,
    ) -> pd.Series | None:

        try:

            return pd.to_datetime(
                series,
                errors="coerce",
                format="mixed",
            )

        except (
            TypeError,
            ValueError,
        ):

            return None


def _finite_float(value: object) -> float | None:
    """Return JSON-safe numeric statistics without inventing a value for NaN."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if pd.notna(numeric) else None
