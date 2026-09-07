from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str
    semantic_type: str
    missing_count: int
    missing_fraction: float
    unique_count: int
    unique_fraction: float


@dataclass(frozen=True)
class DatasetProfile:
    rows: int
    column_count: int

    numeric_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    datetime_candidates: tuple[str, ...]
    spatial_candidates: tuple[str, ...]
    identifier_candidates: tuple[str, ...]

    column_profiles: tuple[ColumnProfile, ...]

    warnings: tuple[str, ...]


class DatasetProfiler:

    SPATIAL_NAMES = {
        "lat",
        "latitude",
        "lon",
        "longitude",
        "x",
        "y",
        "easting",
        "northing",
    }

    IDENTIFIER_HINTS = {
        "id",
        "code",
        "uuid",
        "key",
    }

    def profile(self, df: pd.DataFrame) -> DatasetProfile:

        numeric = []
        categorical = []
        datetime_candidates = []
        spatial = []
        identifiers = []
        column_profiles = []
        warnings = []

        row_count = len(df)

        for column in df.columns:

            series = df[column]

            missing_count = int(series.isna().sum())

            missing_fraction = (
                missing_count / row_count
                if row_count
                else 0.0
            )

            unique_count = int(
                series.nunique(dropna=True)
            )

            unique_fraction = (
                unique_count / row_count
                if row_count
                else 0.0
            )

            semantic_type = self._infer_semantic_type(
                column,
                series,
            )

            if semantic_type == "numeric":
                numeric.append(column)

            elif semantic_type == "categorical":
                categorical.append(column)

            elif semantic_type == "datetime":
                datetime_candidates.append(column)

            elif semantic_type == "spatial":
                spatial.append(column)

            if self._looks_like_identifier(
                column,
                unique_fraction,
            ):
                identifiers.append(column)

            column_profiles.append(
                ColumnProfile(
                    name=column,
                    dtype=str(series.dtype),
                    semantic_type=semantic_type,
                    missing_count=missing_count,
                    missing_fraction=missing_fraction,
                    unique_count=unique_count,
                    unique_fraction=unique_fraction,
                )
            )

            if missing_fraction >= 0.5:
                warnings.append(
                    f"High missingness: {column} "
                    f"({missing_fraction:.1%})"
                )

        return DatasetProfile(
            rows=row_count,
            column_count=len(df.columns),
            numeric_columns=tuple(numeric),
            categorical_columns=tuple(categorical),
            datetime_candidates=tuple(datetime_candidates),
            spatial_candidates=tuple(spatial),
            identifier_candidates=tuple(identifiers),
            column_profiles=tuple(column_profiles),
            warnings=tuple(warnings),
        )

    def _infer_semantic_type(
        self,
        column: str,
        series: pd.Series,
    ) -> str:

        name = column.lower()

        # --------------------------------
        # Spatial columns
        # --------------------------------
        if (
            name in self.SPATIAL_NAMES
            or name.startswith("lat_")
            or name.startswith("lon_")
            or name.startswith("easting")
            or name.startswith("northing")
        ):
            return "spatial"

        # --------------------------------
        # Already parsed datetime
        # --------------------------------
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"

        # --------------------------------
        # Datetime name hints
        # --------------------------------
        datetime_hints = (
            "date",
            "time",
            "timestamp",
            "datetime",
        )

        if any(
            hint in name
            for hint in datetime_hints
        ):

            parsed = pd.to_datetime(
                series,
                errors="coerce",
                format="mixed",
            )

            if (
                len(series) > 0
                and parsed.notna().mean() >= 0.8
            ):
                return "datetime"

        # --------------------------------
        # Object/string columns
        # --------------------------------
        if pd.api.types.is_object_dtype(series):

            parsed = pd.to_datetime(
                series,
                errors="coerce",
                format="mixed",
            )

            if (
                len(series) > 0
                and parsed.notna().mean() >= 0.8
            ):
                return "datetime"

            return "categorical"

        # --------------------------------
        # Numeric columns
        # --------------------------------
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"

        return "unknown"

    def _looks_like_identifier(
        self,
        column: str,
        unique_fraction: float,
    ) -> bool:

        name = column.lower()

        name_hint = (
            name == "id"
            or name.endswith("_id")
            or name.endswith("_code")
            or name.endswith("_key")
            or name in self.IDENTIFIER_HINTS
        )

        high_cardinality = (
            unique_fraction >= 0.95
        )

        return name_hint or high_cardinality

    @staticmethod
    def to_dict(
        profile: DatasetProfile,
    ) -> dict[str, Any]:

        return asdict(profile)