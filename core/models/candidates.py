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
            raise ValueError(f"Target column not found: {target}")

        if df.empty:
            raise ValueError("Cannot generate candidates for an empty dataset.")

        target_series = df[target]
        task = task_type or self._infer_task(target_series)

        if task == "classification":
            candidates = [
                ModelCandidate(
                    "logistic_regression",
                    "linear",
                    "classification",
                    "Interpretable linear classification baseline.",
                    1,
                ),
                ModelCandidate(
                    "random_forest_classifier",
                    "tree_ensemble",
                    "classification",
                    "Robust nonlinear model for mixed tabular relationships.",
                    2,
                ),
                ModelCandidate(
                    "gradient_boosting_classifier",
                    "boosting",
                    "classification",
                    "Strong nonlinear tabular classifier.",
                    3,
                ),
                ModelCandidate(
                    "hist_gradient_boosting_classifier",
                    "boosting",
                    "classification",
                    "Efficient boosting candidate for larger datasets.",
                    4,
                ),
                ModelCandidate(
                    "extra_trees_classifier",
                    "tree_ensemble",
                    "classification",
                    "Randomized tree ensemble with strong nonlinear coverage.",
                    5,
                ),
            ]

        elif task == "regression":
            candidates = [
                ModelCandidate(
                    "linear_regression",
                    "linear",
                    "regression",
                    "Interpretable continuous-target baseline.",
                    1,
                ),
                ModelCandidate(
                    "random_forest_regressor",
                    "tree_ensemble",
                    "regression",
                    "Robust nonlinear regression without feature scaling requirements.",
                    2,
                ),
                ModelCandidate(
                    "gradient_boosting_regressor",
                    "boosting",
                    "regression",
                    "Strong general-purpose nonlinear tabular regressor.",
                    3,
                ),
                ModelCandidate(
                    "hist_gradient_boosting_regressor",
                    "boosting",
                    "regression",
                    "Efficient boosting candidate for larger datasets.",
                    4,
                ),
                ModelCandidate(
                    "extra_trees_regressor",
                    "tree_ensemble",
                    "regression",
                    "Highly randomized ensemble useful for nonlinear relationships.",
                    5,
                ),
            ]

        else:
            raise ValueError(f"Unsupported task type: {task}")

        # Dataset-adaptive pruning.
        # Very small datasets should avoid unnecessary model proliferation.
        if len(df) < 100:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.priority <= 3
            ]

        return ModelCandidateReport(
            task=task,
            candidates=tuple(
                sorted(candidates, key=lambda item: item.priority)
            ),
        )

    @staticmethod
    def _infer_task(target: pd.Series) -> ModelTask:

        if target.dropna().empty:
            raise ValueError("Target column contains no usable values.")

        if pd.api.types.is_bool_dtype(target):
            return "classification"

        if (
            pd.api.types.is_object_dtype(target)
            or pd.api.types.is_string_dtype(target)
            or isinstance(target.dtype, pd.CategoricalDtype)
        ):
            return "classification"

        if not pd.api.types.is_numeric_dtype(target):
            return "classification"

        unique_count = target.nunique(dropna=True)

        if unique_count <= 2:
            return "classification"

        # Small-cardinality integer targets are generally classes,
        # while genuinely continuous numeric targets are regression.
        if (
            pd.api.types.is_integer_dtype(target)
            and unique_count <= min(20, max(2, int(len(target) * 0.05)))
        ):
            return "classification"

        return "regression"
