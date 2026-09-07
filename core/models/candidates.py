from dataclasses import dataclass
from typing import Literal

import pandas as pd


ModelTask = Literal[
    "regression",
    "classification",
]


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    family: str
    task: ModelTask
    reason: str
    priority: int


@dataclass(frozen=True)
class ModelCandidateReport:
    task: ModelTask
    candidates: tuple[ModelCandidate, ...]


class ModelCandidateGenerator:

    def generate(
        self,
        df: pd.DataFrame,
        target: str,
        task_type: ModelTask | None = None,
    ) -> ModelCandidateReport:

        if target not in df.columns:
            raise ValueError(
                f"Target column not found: {target}"
            )

        target_series = df[target]

        task = task_type or self._infer_task(
            target_series
        )

        candidates = []

        # ==========================================================
        # CLASSIFICATION
        # ==========================================================

        if task == "classification":

            candidates.extend([
                ModelCandidate(
                    name="logistic_regression",
                    family="linear",
                    task="classification",
                    reason=(
                        "Strong baseline for "
                        "linearly separable classification."
                    ),
                    priority=1,
                ),
                ModelCandidate(
                    name="random_forest_classifier",
                    family="tree_ensemble",
                    task="classification",
                    reason=(
                        "Handles nonlinear relationships "
                        "and mixed feature interactions."
                    ),
                    priority=2,
                ),
                ModelCandidate(
                    name="gradient_boosting_classifier",
                    family="boosting",
                    task="classification",
                    reason=(
                        "Strong general-purpose model "
                        "for tabular classification."
                    ),
                    priority=3,
                ),
            ])

            # Add extra candidate for sufficiently
            # large datasets.
            if len(df) >= 500:

                candidates.append(
                    ModelCandidate(
                        name="hist_gradient_boosting_classifier",
                        family="boosting",
                        task="classification",
                        reason=(
                            "Efficient boosting candidate "
                            "for larger tabular datasets."
                        ),
                        priority=4,
                    )
                )

        # ==========================================================
        # REGRESSION
        # ==========================================================

        elif task == "regression":

            candidates.extend([
                ModelCandidate(
                    name="linear_regression",
                    family="linear",
                    task="regression",
                    reason=(
                        "Interpretable baseline for "
                        "continuous targets."
                    ),
                    priority=1,
                ),
                ModelCandidate(
                    name="random_forest_regressor",
                    family="tree_ensemble",
                    task="regression",
                    reason=(
                        "Captures nonlinear relationships "
                        "without requiring feature scaling."
                    ),
                    priority=2,
                ),
                ModelCandidate(
                    name="gradient_boosting_regressor",
                    family="boosting",
                    task="regression",
                    reason=(
                        "Strong general-purpose model "
                        "for nonlinear tabular regression."
                    ),
                    priority=3,
                ),
            ])

            if len(df) >= 500:

                candidates.append(
                    ModelCandidate(
                        name="hist_gradient_boosting_regressor",
                        family="boosting",
                        task="regression",
                        reason=(
                            "Efficient boosting candidate "
                            "for larger datasets."
                        ),
                        priority=4,
                    )
                )

        else:
            raise ValueError(
                f"Unsupported task type: {task}"
            )

        return ModelCandidateReport(
            task=task,
            candidates=tuple(
                sorted(
                    candidates,
                    key=lambda item: item.priority,
                )
            ),
        )

    @staticmethod
    def _infer_task(
        target: pd.Series,
    ) -> ModelTask:

        # Boolean → classification
        if pd.api.types.is_bool_dtype(target):
            return "classification"

        # Strings/categories → classification
        if (
            pd.api.types.is_object_dtype(target)
            or pd.api.types.is_string_dtype(target)
            or isinstance(
                target.dtype,
                pd.CategoricalDtype,
            )
        ):
            return "classification"

        # Non-numeric → classification
        if not pd.api.types.is_numeric_dtype(
            target
        ):
            return "classification"

        # Numeric target
        unique_count = target.nunique(
            dropna=True
        )

        # Binary numeric target
        if unique_count <= 2:
            return "classification"

        # Continuous numeric target
        return "regression"