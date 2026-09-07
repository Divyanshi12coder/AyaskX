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

    TARGET_HINTS = {
        "target",
        "label",
        "output",
        "prediction",
        "production",
        "production_t",
        "production_tonnes",
        "shortfall",
        "shortfall_t",
        "shortfall_pct",
        "prospectivity",
        "prospectivity_label",
        "grade",
        "grade_mn_pct",
        "manganese_grade",
        "mn_grade",
        "recovery",
    }

    LEAKAGE_HINTS = {
        "actual",
        "future",
        "next",
        "outcome",
        "risk_score",
        "prediction",
        "predicted",
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

            score = 0.0
            reasons = []

            name = column.lower()

            # -----------------------------
            # Target-name evidence
            # -----------------------------

            if name in self.TARGET_HINTS:
                score += 5.0
                reasons.append("target-name match")

            for hint in self.TARGET_HINTS:
                if hint in name and name != hint:
                    score += 2.0
                    reasons.append(
                        f"name contains '{hint}'"
                    )

            # -----------------------------
            # Avoid obvious identifiers
            # -----------------------------

            if (
                name.endswith("_id")
                or name in self.ID_HINTS
            ):
                score -= 4.0
                reasons.append("identifier-like")

            # -----------------------------
            # Constant columns
            # -----------------------------

            if df[column].nunique(
                dropna=True
            ) <= 1:
                score -= 5.0
                reasons.append("constant")

            # -----------------------------
            # Datetime columns
            # -----------------------------

            if pd.api.types.is_datetime64_any_dtype(
                df[column]
            ):
                score -= 3.0
                reasons.append("datetime")

            # -----------------------------
            # High cardinality
            # -----------------------------

            non_null = df[column].notna().sum()

            if non_null > 0:

                unique_fraction = (
                    df[column].nunique(
                        dropna=True
                    )
                    / non_null
                )

                if unique_fraction > 0.98:
                    score -= 3.0
                    reasons.append(
                        "near-unique values"
                    )

            if score > 0:

                candidates.append(
                    TargetCandidate(
                        column=column,
                        score=score,
                        reason=", ".join(reasons),
                    )
                )

        candidates.sort(
            key=lambda x: x.score,
            reverse=True,
        )

        if not candidates:

            return TaskDetectionResult(
                task_type="unknown",
                target=None,
                feature_columns=tuple(df.columns),
                candidates=(),
                confidence=0.0,
                warnings=(
                    "No plausible target detected.",
                ),
            )

        best = candidates[0]

        target = best.column

        feature_columns = tuple(
            column
            for column in df.columns
            if column != target
        )

        task_type = self._infer_task_type(
            df[target]
        )

        confidence = min(
            1.0,
            best.score / 8.0,
        )

        # Spatial task detection
        spatial_columns = {
            column.lower()
            for column in df.columns
        }

        has_latitude = (
            "latitude" in spatial_columns
            or "lat" in spatial_columns
        )

        has_longitude = (
            "longitude" in spatial_columns
            or "lon" in spatial_columns
        )

        if has_latitude and has_longitude:

            if task_type == "classification":
                task_type = "spatial_classification"

            elif task_type == "regression":
                task_type = "spatial_regression"

        # Warn about suspicious target names
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

    @staticmethod
    def _infer_task_type(
        series: pd.Series,
    ) -> TaskType:

        if pd.api.types.is_bool_dtype(series):
            return "classification"

        if pd.api.types.is_numeric_dtype(series):

            unique_count = series.nunique(
                dropna=True
            )

            # Binary / low-cardinality numeric labels
            if unique_count <= 10:
                return "classification"

            return "regression"

        return "classification"