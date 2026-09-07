from dataclasses import dataclass
from typing import Literal

import pandas as pd


TaskType = Literal[
    "classification",
    "regression",
    "spatial_classification",
    "spatial_regression",
    "unknown",
]


@dataclass(frozen=True)
class TargetCandidate:
    column: str
    score: float
    reason: str


@dataclass(frozen=True)
class TaskDetectionResult:
    task_type: TaskType
    target: str | None
    feature_columns: tuple[str, ...]
    candidates: tuple[TargetCandidate, ...]
    confidence: float
    warnings: tuple[str, ...]


class TaskDetector:

    CLASSIFICATION_HINTS = {
        "label",
        "class",
        "category",
        "type",
        "flag",
        "status",
        "risk",
        "prospectivity_label",
        "shortfall_flag",
    }

    REGRESSION_HINTS = {
        "grade",
        "mn_grade",
        "manganese_grade",
        "grade_mn_pct",
        "production",
        "production_t",
        "production_tonnes",
        "tonnage",
        "tonnes",
        "recovery",
        "recovery_pct",
        "ore_available",
        "ore_available_t",
        "quantity",
        "amount",
        "value",
    }

    TARGET_HINTS = (
        CLASSIFICATION_HINTS
        | REGRESSION_HINTS
        | {
            "target",
            "output",
            "prediction",
            "shortfall",
            "prospectivity",
        }
    )

    LEAKAGE_HINTS = {
        "actual",
        "future",
        "next",
        "outcome",
        "predicted",
        "prediction",
    }

    ID_HINTS = {
        "id",
        "uuid",
        "key",
        "code",
    }

    def detect(
        self,
        df: pd.DataFrame,
    ) -> TaskDetectionResult:

        candidates = []
        warnings = []

        for column in df.columns:

            name = column.lower()

            score = 0.0
            reasons = []

            # --------------------------------
            # Exact target-name match
            # --------------------------------

            if name in self.TARGET_HINTS:
                score += 6.0
                reasons.append(
                    "target-name match"
                )

            # --------------------------------
            # Regression semantic evidence
            # --------------------------------

            for hint in self.REGRESSION_HINTS:

                if hint in name:

                    score += 4.0

                    reasons.append(
                        f"regression semantic: {hint}"
                    )

                    break

            # --------------------------------
            # Classification semantic evidence
            # --------------------------------

            for hint in self.CLASSIFICATION_HINTS:

                if hint in name:

                    score += 4.0

                    reasons.append(
                        f"classification semantic: {hint}"
                    )

                    break

            # --------------------------------
            # Generic target wording
            # --------------------------------

            if (
                "target" in name
                or "output" in name
            ):

                score += 2.0

                reasons.append(
                    "generic target indicator"
                )

            # --------------------------------
            # Identifier penalty
            # --------------------------------

            if (
                name.endswith("_id")
                or name.endswith("_code")
                or name.endswith("_key")
                or name in self.ID_HINTS
            ):

                score -= 5.0

                reasons.append(
                    "identifier-like"
                )

            # --------------------------------
            # Constant penalty
            # --------------------------------

            if df[column].nunique(
                dropna=True
            ) <= 1:

                score -= 5.0

                reasons.append(
                    "constant"
                )

            # --------------------------------
            # Datetime penalty
            # --------------------------------

            if pd.api.types.is_datetime64_any_dtype(
                df[column]
            ):

                score -= 4.0

                reasons.append(
                    "datetime"
                )

            # --------------------------------
            # Near-unique penalty
            # --------------------------------

            non_null = int(
                df[column].notna().sum()
            )

            if non_null > 0:

                unique_fraction = (
                    df[column].nunique(
                        dropna=True
                    )
                    / non_null
                )

                if unique_fraction >= 0.98:

                    score -= 3.0

                    reasons.append(
                        "near-unique values"
                    )

            # --------------------------------
            # Candidate
            # --------------------------------

            if score > 0:

                candidates.append(
                    TargetCandidate(
                        column=column,
                        score=score,
                        reason=", ".join(
                            reasons
                        ),
                    )
                )

        candidates.sort(
            key=lambda candidate: candidate.score,
            reverse=True,
        )

        # --------------------------------
        # No target
        # --------------------------------

        if not candidates:

            return TaskDetectionResult(
                task_type="unknown",
                target=None,
                feature_columns=tuple(
                    df.columns
                ),
                candidates=(),
                confidence=0.0,
                warnings=(
                    "No plausible target detected.",
                ),
            )

        # --------------------------------
        # Best target
        # --------------------------------

        best = candidates[0]

        target = best.column

        feature_columns = tuple(
            column
            for column in df.columns
            if column != target
        )

        # --------------------------------
        # Task type
        # --------------------------------

        task_type = self._infer_task_type(
            target,
            df[target],
        )

        confidence = min(
            1.0,
            best.score / 10.0,
        )

        # --------------------------------
        # Spatial detection
        # --------------------------------

        normalized_columns = {
            column.lower()
            for column in df.columns
        }

        has_latitude = (
            "latitude" in normalized_columns
            or "lat" in normalized_columns
        )

        has_longitude = (
            "longitude" in normalized_columns
            or "lon" in normalized_columns
        )

        if has_latitude and has_longitude:

            if task_type == "classification":

                task_type = (
                    "spatial_classification"
                )

            elif task_type == "regression":

                task_type = (
                    "spatial_regression"
                )

        # --------------------------------
        # Leakage warning
        # --------------------------------

        if any(
            hint in target.lower()
            for hint in self.LEAKAGE_HINTS
        ):

            warnings.append(
                f"Target '{target}' requires "
                "leakage review before training."
            )

        return TaskDetectionResult(
            task_type=task_type,
            target=target,
            feature_columns=feature_columns,
            candidates=tuple(candidates),
            confidence=confidence,
            warnings=tuple(warnings),
        )

    def _infer_task_type(
        self,
        column: str,
        series: pd.Series,
    ) -> TaskType:

        name = column.lower()

        # --------------------------------
        # Strong semantic regression signal
        # --------------------------------

        if any(
            hint in name
            for hint in self.REGRESSION_HINTS
        ):

            return "regression"

        # --------------------------------
        # Strong semantic classification
        # --------------------------------

        if any(
            hint in name
            for hint in self.CLASSIFICATION_HINTS
        ):

            return "classification"

        # --------------------------------
        # Boolean
        # --------------------------------

        if pd.api.types.is_bool_dtype(
            series
        ):

            return "classification"

        # --------------------------------
        # Numeric fallback
        # --------------------------------

        if pd.api.types.is_numeric_dtype(
            series
        ):

            unique_count = series.nunique(
                dropna=True
            )

            row_count = len(
                series.dropna()
            )

            if row_count == 0:
                return "unknown"

            unique_fraction = (
                unique_count / row_count
            )

            # Only call a numeric target
            # classification when there is
            # genuinely strong evidence.
            if (
                unique_count <= 2
                and unique_fraction <= 0.5
            ):
                return "classification"

            return "regression"

        # --------------------------------
        # String / categorical fallback
        # --------------------------------

        return "classification"