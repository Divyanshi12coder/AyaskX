from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PreprocessingRecommendation:
    column: str
    role: str
    actions: tuple[str, ...]
    reason: str
    confidence: float


@dataclass(frozen=True)
class PreprocessingPlan:
    recommendations: tuple[PreprocessingRecommendation, ...]
    numeric_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    boolean_columns: tuple[str, ...]
    temporal_columns: tuple[str, ...]
    spatial_columns: tuple[str, ...]
    identifier_columns: tuple[str, ...]
    drop_columns: tuple[str, ...]


class PreprocessingRecommender:

    def recommend(
        self,
        df: pd.DataFrame,
        target: str | None = None,
    ) -> PreprocessingPlan:

        recommendations = []

        numeric = []
        categorical = []
        boolean = []
        temporal = []
        spatial = []
        identifiers = []
        drop_columns = []

        for column in df.columns:

            if column == target:
                continue

            series = df[column]
            name = column.lower()

            actions = []
            reason_parts = []
            role = "unknown"
            confidence = 0.70

            # --------------------------------
            # Spatial
            # --------------------------------

            if name in {
                "latitude",
                "lat",
                "latitude_deg",
                "lat_deg",
                "longitude",
                "lon",
                "lng",
                "longitude_deg",
                "lon_deg",
            }:

                role = "spatial"
                spatial.append(column)

                actions.append("retain")

                reason_parts.append(
                    "spatial coordinate"
                )

                confidence = 0.98

            # --------------------------------
            # Identifier
            # --------------------------------

            elif (
                name in {
                    "id",
                    "uuid",
                    "identifier",
                    "key",
                    "code",
                }
                or name.endswith("_id")
                or name.endswith("_uuid")
                or name.endswith("_key")
                or name.endswith("_code")
            ):

                role = "identifier"
                identifiers.append(column)

                actions.append(
                    "exclude_from_default_features"
                )

                reason_parts.append(
                    "identifier-like column"
                )

                confidence = 0.98

            # --------------------------------
            # Boolean
            # --------------------------------

            elif pd.api.types.is_bool_dtype(
                series
            ):

                role = "boolean"
                boolean.append(column)

                actions.append(
                    "encode_binary"
                )

                reason_parts.append(
                    "boolean feature"
                )

                confidence = 1.0

            # --------------------------------
            # Datetime
            # --------------------------------

            elif pd.api.types.is_datetime64_any_dtype(
                series
            ):

                role = "temporal"
                temporal.append(column)

                actions.extend([
                    "extract_year",
                    "extract_month",
                    "extract_day",
                    "extract_day_of_week",
                ])

                reason_parts.append(
                    "datetime feature"
                )

                confidence = 1.0

            # --------------------------------
            # Temporal strings
            # --------------------------------

            elif self._looks_temporal(
                series,
                name,
            ):

                role = "temporal"
                temporal.append(column)

                actions.extend([
                    "parse_datetime",
                    "extract_year",
                    "extract_month",
                    "extract_day",
                    "extract_day_of_week",
                ])

                reason_parts.append(
                    "datetime-like string"
                )

                confidence = 0.90

            # --------------------------------
            # Numeric
            # --------------------------------

            elif pd.api.types.is_numeric_dtype(
                series
            ):

                role = "numeric"
                numeric.append(column)

                actions.append(
                    "median_imputation"
                )

                # Missingness
                missing_fraction = (
                    series.isna().mean()
                )

                if missing_fraction > 0:
                    reason_parts.append(
                        "missing values present"
                    )
                else:
                    reason_parts.append(
                        "numeric feature"
                    )

                # Skewness
                clean = series.dropna()

                if len(clean) >= 8:

                    skew = clean.skew()

                    if pd.notna(skew) and abs(
                        float(skew)
                    ) > 1.0:

                        actions.append(
                            "consider_log_or_power_transform"
                        )

                        reason_parts.append(
                            "strong skew detected"
                        )

                # Scaling recommendation
                actions.append(
                    "scale_if_model_requires_it"
                )

                confidence = 0.95

            # --------------------------------
            # Categorical
            # --------------------------------

            elif isinstance(
                series.dtype,
                pd.CategoricalDtype,
            ) or pd.api.types.is_object_dtype(
                series
            ) or pd.api.types.is_string_dtype(
                series
            ):

                non_null = series.dropna()

                if len(non_null) == 0:

                    role = "categorical"

                    categorical.append(
                        column
                    )

                    actions.append(
                        "constant_or_empty_review"
                    )

                    reason_parts.append(
                        "empty categorical feature"
                    )

                else:

                    unique_count = (
                        non_null.nunique()
                    )

                    unique_fraction = (
                        unique_count
                        / len(non_null)
                    )

                    # High cardinality
                    if (
                        unique_fraction >= 0.95
                        and unique_count > 20
                    ):

                        role = "categorical"

                        categorical.append(
                            column
                        )

                        actions.append(
                            "review_high_cardinality"
                        )

                        actions.append(
                            "consider_frequency_or_target_encoding"
                        )

                        reason_parts.append(
                            "high-cardinality categorical"
                        )

                        confidence = 0.90

                    else:

                        role = "categorical"

                        categorical.append(
                            column
                        )

                        actions.append(
                            "most_frequent_imputation"
                        )

                        actions.append(
                            "one_hot_or_ordinal_encoding"
                        )

                        reason_parts.append(
                            "categorical feature"
                        )

                        confidence = 0.90

            # --------------------------------
            # Unknown
            # --------------------------------

            else:

                role = "unknown"

                actions.append(
                    "manual_review"
                )

                reason_parts.append(
                    f"unsupported dtype: {series.dtype}"
                )

                confidence = 0.40

            recommendations.append(
                PreprocessingRecommendation(
                    column=column,
                    role=role,
                    actions=tuple(actions),
                    reason="; ".join(
                        reason_parts
                    ),
                    confidence=confidence,
                )
            )

        return PreprocessingPlan(
            recommendations=tuple(
                recommendations
            ),
            numeric_columns=tuple(numeric),
            categorical_columns=tuple(
                categorical
            ),
            boolean_columns=tuple(boolean),
            temporal_columns=tuple(temporal),
            spatial_columns=tuple(spatial),
            identifier_columns=tuple(
                identifiers
            ),
            drop_columns=tuple(
                drop_columns
            ),
        )

    @staticmethod
    def _looks_temporal(
        series: pd.Series,
        name: str,
    ) -> bool:

        temporal_hints = (
            "date",
            "timestamp",
            "datetime",
        )

        if any(
            hint in name
            for hint in temporal_hints
        ):

            if pd.api.types.is_numeric_dtype(
                series
            ):
                return False

            return True

        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            return False

        non_null = series.dropna()

        if len(non_null) < 2:
            return False

        sample = non_null.astype(
            str
        ).head(100)

        parsed = pd.to_datetime(
            sample,
            errors="coerce",
            format="mixed",
        )

        return (
            parsed.notna().mean()
            >= 0.90
        )