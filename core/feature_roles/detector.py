from dataclasses import dataclass
from typing import Literal

import pandas as pd


FeatureRole = Literal[
    "target",
    "identifier",
    "spatial",
    "temporal",
    "numeric",
    "categorical",
    "boolean",
    "text",
    "unknown",
]


@dataclass(frozen=True)
class FeatureRoleInfo:
    column: str
    role: FeatureRole
    confidence: float
    reason: str


@dataclass(frozen=True)
class FeatureRoleReport:
    target: str | None
    roles: tuple[FeatureRoleInfo, ...]
    target_columns: tuple[str, ...]
    identifier_columns: tuple[str, ...]
    spatial_columns: tuple[str, ...]
    temporal_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    boolean_columns: tuple[str, ...]
    text_columns: tuple[str, ...]
    unknown_columns: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        role_map = {item.column: item.role for item in self.roles}
        dropped = list(self.identifier_columns) + list(self.unknown_columns)
        return {
            "target": self.target,
            "roles": role_map,
            "role_details": [
                {"column": item.column, "role": item.role,
                 "confidence": item.confidence, "reason": item.reason}
                for item in self.roles
            ],
            "features": [
                item.column for item in self.roles
                if item.role in {"numeric", "categorical", "boolean", "text", "spatial", "temporal"}
            ],
            "dropped_columns": dropped,
            "target_columns": list(self.target_columns),
            "identifier_columns": list(self.identifier_columns),
            "spatial_columns": list(self.spatial_columns),
            "temporal_columns": list(self.temporal_columns),
            "numeric_columns": list(self.numeric_columns),
            "categorical_columns": list(self.categorical_columns),
            "boolean_columns": list(self.boolean_columns),
            "text_columns": list(self.text_columns),
            "unknown_columns": list(self.unknown_columns),
        }


class FeatureRoleDetector:

    LATITUDE_NAMES = {
        "latitude",
        "lat",
        "lat_deg",
        "latitude_deg",
    }

    LONGITUDE_NAMES = {
        "longitude",
        "lon",
        "lng",
        "long",
        "lon_deg",
        "longitude_deg",
    }

    TEMPORAL_HINTS = {
        "date",
        "time",
        "timestamp",
        "datetime",
        "year",
        "month",
        "day",
        "week",
    }

    ID_SUFFIXES = (
        "_id",
        "_uuid",
        "_key",
        "_code",
    )

    ID_EXACT_NAMES = {
        "id",
        "uuid",
        "identifier",
        "key",
        "code",
    }

    def detect(
        self,
        df: pd.DataFrame,
        target: str | None = None,
    ) -> FeatureRoleReport:

        roles = []

        for column in df.columns:

            role, confidence, reason = self._detect_column(
                df,
                column,
                target,
            )

            roles.append(
                FeatureRoleInfo(
                    column=column,
                    role=role,
                    confidence=confidence,
                    reason=reason,
                )
            )

        return FeatureRoleReport(
            target=target,
            roles=tuple(roles),

            target_columns=tuple(
                item.column
                for item in roles
                if item.role == "target"
            ),

            identifier_columns=tuple(
                item.column
                for item in roles
                if item.role == "identifier"
            ),

            spatial_columns=tuple(
                item.column
                for item in roles
                if item.role == "spatial"
            ),

            temporal_columns=tuple(
                item.column
                for item in roles
                if item.role == "temporal"
            ),

            numeric_columns=tuple(
                item.column
                for item in roles
                if item.role == "numeric"
            ),

            categorical_columns=tuple(
                item.column
                for item in roles
                if item.role == "categorical"
            ),

            boolean_columns=tuple(
                item.column
                for item in roles
                if item.role == "boolean"
            ),

            text_columns=tuple(
                item.column
                for item in roles
                if item.role == "text"
            ),

            unknown_columns=tuple(
                item.column
                for item in roles
                if item.role == "unknown"
            ),
        )

    def _detect_column(
        self,
        df: pd.DataFrame,
        column: str,
        target: str | None,
    ):

        series = df[column]
        name = column.lower().strip()

        # ---------------------------------
        # Target
        # ---------------------------------

        if target is not None and column == target:

            return (
                "target",
                1.0,
                "explicitly supplied target",
            )

        # ---------------------------------
        # Spatial
        # ---------------------------------

        if (
            name in self.LATITUDE_NAMES
            or name in self.LONGITUDE_NAMES
        ):

            return (
                "spatial",
                1.0,
                "latitude/longitude semantic name",
            )

        # ---------------------------------
        # Identifier
        # ---------------------------------

        if (
            name in self.ID_EXACT_NAMES
            or name.endswith(self.ID_SUFFIXES)
        ):

            return (
                "identifier",
                0.98,
                "identifier semantic name",
            )

        # ---------------------------------
        # Datetime dtype
        # ---------------------------------

        if pd.api.types.is_datetime64_any_dtype(
            series
        ):

            return (
                "temporal",
                1.0,
                "datetime dtype",
            )

        # ---------------------------------
        # Detect datetime-like strings
        # ---------------------------------

        if self._looks_temporal(
            series,
            name,
        ):

            return (
                "temporal",
                0.90,
                "datetime-like values or temporal name",
            )

        # ---------------------------------
        # Boolean
        # ---------------------------------

        if pd.api.types.is_bool_dtype(series):

            return (
                "boolean",
                1.0,
                "boolean dtype",
            )

        # ---------------------------------
        # Numeric
        # ---------------------------------

        if pd.api.types.is_numeric_dtype(series):

            return (
                "numeric",
                1.0,
                "numeric dtype",
            )

        # ---------------------------------
        # Categorical
        # ---------------------------------

        if isinstance(
            series.dtype,
            pd.CategoricalDtype,
        ):

            return (
                "categorical",
                1.0,
                "pandas categorical dtype",
            )

        # ---------------------------------
        # Object/string analysis
        # ---------------------------------

        if (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):

            non_null = series.dropna()

            if len(non_null) == 0:

                return (
                    "unknown",
                    0.40,
                    "empty column",
                )

            unique_fraction = (
                non_null.nunique()
                / len(non_null)
            )

            avg_length = non_null.astype(
                str
            ).str.len().mean()

            # Low-cardinality text
            if unique_fraction <= 0.20:

                return (
                    "categorical",
                    0.85,
                    "low-cardinality string column",
                )

            # Long free-form text
            if avg_length >= 80:

                return (
                    "text",
                    0.90,
                    "long free-form text",
                )

            # Short/medium high-cardinality strings
            return (
                "categorical",
                0.70,
                "string column",
            )

        # ---------------------------------
        # Fallback
        # ---------------------------------

        return (
            "unknown",
            0.30,
            f"unsupported dtype: {series.dtype}",
        )

    def _looks_temporal(
        self,
        series: pd.Series,
        name: str,
    ) -> bool:

        # Semantic name is useful evidence.
        if any(
            hint in name
            for hint in self.TEMPORAL_HINTS
        ):

            # Avoid treating ordinary numeric
            # measures such as "downtime_hours"
            # as datetime merely because they
            # contain "time".
            if pd.api.types.is_numeric_dtype(
                series
            ):

                return False

            return True

        # Try parsing object/string columns.
        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):

            return False

        non_null = series.dropna()

        if len(non_null) < 2:

            return False

        sample = non_null.astype(str).head(100)

        parsed = pd.to_datetime(
            sample,
            errors="coerce",
            format="mixed",
        )

        success_fraction = (
            parsed.notna().mean()
        )

        return success_fraction >= 0.90
