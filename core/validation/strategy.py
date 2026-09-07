from dataclasses import dataclass
from typing import Literal

import pandas as pd


ValidationType = Literal[
    "spatial_holdout",
    "temporal_holdout",
    "group_holdout",
    "stratified_holdout",
    "random_holdout",
]


@dataclass(frozen=True)
class ValidationStrategy:
    strategy: ValidationType
    primary_column: str | None
    secondary_column: str | None
    reason: str
    confidence: float


class ValidationStrategySelector:

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

    TIME_HINTS = (
        "date",
        "time",
        "timestamp",
        "datetime",
    )

    GROUP_HINTS = {
        "mine_id",
        "site_id",
        "equipment_id",
        "machine_id",
        "block_id",
        "location_id",
    }

    def select(
        self,
        df: pd.DataFrame,
        target: str | None = None,
    ) -> ValidationStrategy:

        columns = list(df.columns)

        normalized = {
            column.lower().strip(): column
            for column in columns
        }

        # ==========================================================
        # 1. SPATIAL VALIDATION
        # ==========================================================

        latitude = self._find_column(
            normalized,
            self.LATITUDE_NAMES,
        )

        longitude = self._find_column(
            normalized,
            self.LONGITUDE_NAMES,
        )

        if latitude and longitude:

            return ValidationStrategy(
                strategy="spatial_holdout",
                primary_column=latitude,
                secondary_column=longitude,
                reason=(
                    "Latitude and longitude detected; "
                    "geographic holdout reduces spatial "
                    "leakage and tests geographic "
                    "generalization."
                ),
                confidence=0.98,
            )

        # ==========================================================
        # 2. GROUP VALIDATION
        # ==========================================================
        #
        # IMPORTANT:
        # Group identifiers are checked BEFORE generic
        # datetime inference.
        #
        # Example:
        # mine_id = M1, M2, M3
        #
        # This must NOT accidentally become temporal.
        # ==========================================================

        group = self._find_column(
            normalized,
            self.GROUP_HINTS,
        )

        if group:

            unique_count = df[group].nunique(
                dropna=True
            )

            if (
                unique_count >= 2
                and unique_count < len(df)
            ):

                return ValidationStrategy(
                    strategy="group_holdout",
                    primary_column=group,
                    secondary_column=None,
                    reason=(
                        "Entity/group identifier detected; "
                        "group-aware validation prevents "
                        "the same entity appearing across "
                        "training and validation."
                    ),
                    confidence=0.95,
                )

        # ==========================================================
        # 3. TEMPORAL VALIDATION
        # ==========================================================

        temporal = self._find_temporal_column(df)

        if temporal:

            return ValidationStrategy(
                strategy="temporal_holdout",
                primary_column=temporal,
                secondary_column=None,
                reason=(
                    "Temporal information detected; "
                    "chronological validation prevents "
                    "future information from entering "
                    "the training set."
                ),
                confidence=0.95,
            )

        # ==========================================================
        # 4. STRATIFIED CLASSIFICATION VALIDATION
        # ==========================================================

        if target is not None and target in df:

            target_series = df[target]

            if self._looks_classification(
                target_series
            ):

                return ValidationStrategy(
                    strategy="stratified_holdout",
                    primary_column=target,
                    secondary_column=None,
                    reason=(
                        "Low-cardinality target detected; "
                        "stratification preserves class "
                        "distribution."
                    ),
                    confidence=0.85,
                )

        # ==========================================================
        # 5. RANDOM HOLDOUT FALLBACK
        # ==========================================================

        return ValidationStrategy(
            strategy="random_holdout",
            primary_column=None,
            secondary_column=None,
            reason=(
                "No strong spatial, temporal, or "
                "group structure detected."
            ),
            confidence=0.70,
        )

    # ==============================================================
    # COLUMN FINDER
    # ==============================================================

    @staticmethod
    def _find_column(
        normalized: dict[str, str],
        names: set[str],
    ) -> str | None:

        for name in names:

            if name in normalized:
                return normalized[name]

        return None

    # ==============================================================
    # TEMPORAL DETECTION
    # ==============================================================

    def _find_temporal_column(
        self,
        df: pd.DataFrame,
    ) -> str | None:

        # ----------------------------------------------------------
        # First: actual datetime dtype
        # ----------------------------------------------------------

        for column in df.columns:

            if self._is_identifier(column):
                continue

            if pd.api.types.is_datetime64_any_dtype(
                df[column]
            ):

                return column

        # ----------------------------------------------------------
        # Second: semantic temporal names
        # ----------------------------------------------------------

        for column in df.columns:

            if self._is_identifier(column):
                continue

            name = column.lower().strip()

            if any(
                hint in name
                for hint in self.TIME_HINTS
            ):

                # Numeric columns containing "time"
                # such as downtime_hours should not
                # automatically become temporal.
                if pd.api.types.is_numeric_dtype(
                    df[column]
                ):
                    continue

                return column

        # ----------------------------------------------------------
        # Third: parse string columns
        # ----------------------------------------------------------

        for column in df.columns:

            if self._is_identifier(column):
                continue

            series = df[column]

            if not (
                pd.api.types.is_object_dtype(series)
                or pd.api.types.is_string_dtype(series)
            ):
                continue

            non_null = series.dropna()

            if len(non_null) < 3:
                continue

            sample = non_null.astype(
                str
            ).head(100)

            parsed = pd.to_datetime(
                sample,
                errors="coerce",
                format="mixed",
            )

            success_fraction = (
                parsed.notna().mean()
            )

            if success_fraction >= 0.90:
                return column

        return None

    # ==============================================================
    # IDENTIFIER CHECK
    # ==============================================================

    @staticmethod
    def _is_identifier(
        column: str,
    ) -> bool:

        name = column.lower().strip()

        if name in {
            "id",
            "uuid",
            "identifier",
            "key",
            "code",
        }:
            return True

        if name.endswith("_id"):
            return True

        if name.endswith("_uuid"):
            return True

        if name.endswith("_key"):
            return True

        if name.endswith("_code"):
            return True

        return False

    # ==============================================================
    # CLASSIFICATION DETECTION
    # ==============================================================

    @staticmethod
    def _looks_classification(
        series: pd.Series,
    ) -> bool:

        # Boolean target
        if pd.api.types.is_bool_dtype(series):
            return True

        # Strings / categories are classification-like
        if (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or isinstance(
                series.dtype,
                pd.CategoricalDtype,
            )
        ):
            return True

        # Non-numeric data
        if not pd.api.types.is_numeric_dtype(
            series
        ):
            return True

        unique_count = series.nunique(
            dropna=True
        )

        # Binary numeric target
        if unique_count <= 2:
            return True

        return False