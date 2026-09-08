from dataclasses import dataclass

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import (
    GroupShuffleSplit,
    StratifiedShuffleSplit,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from core.models.splitters import SplitResult


@dataclass(frozen=True)
class ModelEvaluation:
    model_name: str
    task: str
    primary_metric: float
    metrics: dict[str, float]


@dataclass(frozen=True)
class TrainingResult:
    evaluations: tuple[ModelEvaluation, ...]
    best_model_name: str | None
    best_score: float | None


class ModelTrainer:

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    def __init__(self) -> None:
        # Stores fitted sklearn pipelines by model_name after training.
        # Populated additively in train_on_split; does not affect outputs.
        self._fitted_pipelines: dict[str, "Pipeline"] = {}

    def get_fitted_pipeline(self, model_name: str) -> "Pipeline | None":
        """Return the last fitted sklearn Pipeline for a given model_name."""
        return self._fitted_pipelines.get(model_name)

    def train_and_evaluate(
        self,
        df: pd.DataFrame,
        target: str,
        task_type: str,
        candidates: list[str] | tuple[str, ...],
        validation_strategy: str = "random_holdout",
        group_column: str | None = None,
        time_column: str | None = None,
        latitude_column: str | None = None,
        longitude_column: str | None = None,
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> TrainingResult:

        if target not in df.columns:
            raise ValueError(
                f"Target column not found: {target}"
            )

        if not 0 < test_size < 1:
            raise ValueError(
                "test_size must be between 0 and 1."
            )

        clean_df = df.dropna(
            subset=[target]
        ).copy()

        if len(clean_df) < 4:
            raise ValueError(
                "Dataset is too small for model training."
            )

        X = clean_df.drop(
            columns=[target]
        )

        y = clean_df[target]

        # ------------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT remove identifiers before creating the split.
        #
        # mine_id, for example, may be an identifier for the
        # model but is still required for group_holdout.
        # ------------------------------------------------------

        split = self._create_split(
            X=X,
            y=y,
            strategy=validation_strategy,
            group_column=group_column,
            time_column=time_column,
            latitude_column=latitude_column,
            longitude_column=longitude_column,
            test_size=test_size,
            random_state=random_state,
        )

        # ------------------------------------------------------
        # Remove identifiers AFTER validation split.
        # ------------------------------------------------------

        split = SplitResult(
            X_train=self._remove_identifiers(
                split.X_train
            ),
            X_test=self._remove_identifiers(
                split.X_test
            ),
            y_train=split.y_train,
            y_test=split.y_test,
        )

        if split.X_train.shape[1] == 0:
            raise ValueError(
                "No usable features remain after "
                "identifier removal."
            )

        return self.train_on_split(
            split=split,
            task_type=task_type,
            candidates=candidates,
            random_state=random_state,
        )

    # ==========================================================
    # TRAIN ON PRE-CREATED SPLIT
    # ==========================================================

    def train_on_split(
        self,
        split: SplitResult,
        task_type: str,
        candidates: list[str] | tuple[str, ...],
        random_state: int = 42,
    ) -> TrainingResult:

        X_train = split.X_train
        X_test = split.X_test

        y_train = split.y_train
        y_test = split.y_test

        if len(X_train) == 0:
            raise ValueError(
                "Training split is empty."
            )

        if len(X_test) == 0:
            raise ValueError(
                "Test split is empty."
            )

        if len(candidates) == 0:
            return TrainingResult(
                evaluations=(),
                best_model_name=None,
                best_score=None,
            )

        evaluations = []

        for model_name in candidates:

            model = self._build_model(
                model_name=model_name,
                task_type=task_type,
                random_state=random_state,
            )

            preprocessor = self._build_preprocessor(
                X_train
            )

            pipeline = Pipeline([
                (
                    "preprocessing",
                    preprocessor,
                ),
                (
                    "model",
                    model,
                ),
            ])

            try:
                pipeline.fit(
                    X_train,
                    y_train,
                )

                # Store fitted pipeline for later retrieval (additive, no API change)
                self._fitted_pipelines[model_name] = pipeline

                predictions = pipeline.predict(
                    X_test
                )

                evaluation = self._evaluate(
                    model_name=model_name,
                    task_type=task_type,
                    y_true=y_test,
                    predictions=predictions,
                )

                evaluations.append(
                    evaluation
                )

            except Exception:
                # Skip this candidate â€” a single model failure should not
                # prevent other candidates from being evaluated.
                continue

        if not evaluations:
            return TrainingResult(
                evaluations=(),
                best_model_name=None,
                best_score=None,
            )

        # Higher is better:
        #
        # Regression     -> R2
        # Classification -> weighted F1
        #
        best = max(
            evaluations,
            key=lambda item: item.primary_metric,
        )

        return TrainingResult(
            evaluations=tuple(evaluations),
            best_model_name=best.model_name,
            best_score=best.primary_metric,
        )

    # ==========================================================
    # VALIDATION SPLITTING
    # ==========================================================

    def _create_split(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        strategy: str,
        group_column: str | None,
        time_column: str | None,
        latitude_column: str | None,
        longitude_column: str | None,
        test_size: float,
        random_state: int,
    ) -> SplitResult:

        # ======================================================
        # GROUP HOLDOUT
        # ======================================================

        if strategy == "group_holdout":

            if group_column is None:
                raise ValueError(
                    "group_column is required "
                    "for group_holdout."
                )

            if group_column not in X.columns:
                raise ValueError(
                    f"Group column not found: "
                    f"{group_column}"
                )

            groups = X[group_column]

            splitter = GroupShuffleSplit(
                n_splits=1,
                test_size=test_size,
                random_state=random_state,
            )

            train_idx, test_idx = next(
                splitter.split(
                    X,
                    y,
                    groups=groups,
                )
            )

            return SplitResult(
                X_train=X.iloc[train_idx],
                X_test=X.iloc[test_idx],
                y_train=y.iloc[train_idx],
                y_test=y.iloc[test_idx],
            )

        # ======================================================
        # STRATIFIED HOLDOUT
        # ======================================================

        if strategy == "stratified_holdout":

            splitter = StratifiedShuffleSplit(
                n_splits=1,
                test_size=test_size,
                random_state=random_state,
            )

            train_idx, test_idx = next(
                splitter.split(X, y)
            )

            return SplitResult(
                X_train=X.iloc[train_idx],
                X_test=X.iloc[test_idx],
                y_train=y.iloc[train_idx],
                y_test=y.iloc[test_idx],
            )

        # ======================================================
        # TEMPORAL HOLDOUT
        # ======================================================

        if strategy == "temporal_holdout":

            if time_column is None:
                raise ValueError(
                    "time_column is required "
                    "for temporal_holdout."
                )

            if time_column not in X.columns:
                raise ValueError(
                    f"Time column not found: "
                    f"{time_column}"
                )

            parsed_time = pd.to_datetime(
                X[time_column],
                errors="coerce",
                format="mixed",
            )

            if parsed_time.isna().any():
                raise ValueError(
                    "Temporal column contains values "
                    "that cannot be parsed as datetime."
                )

            order = np.argsort(
                parsed_time.to_numpy()
            )

            X_sorted = X.iloc[order]
            y_sorted = y.iloc[order]

            split_index = int(
                len(X_sorted) * (1 - test_size)
            )

            if split_index <= 0:
                raise ValueError(
                    "Temporal training split is empty."
                )

            if split_index >= len(X_sorted):
                raise ValueError(
                    "Temporal test split is empty."
                )

            return SplitResult(
                X_train=X_sorted.iloc[:split_index],
                X_test=X_sorted.iloc[split_index:],
                y_train=y_sorted.iloc[:split_index],
                y_test=y_sorted.iloc[split_index:],
            )

        # ======================================================
        # SPATIAL HOLDOUT
        # ======================================================

        if strategy == "spatial_holdout":

            if (
                latitude_column is None
                or longitude_column is None
            ):
                raise ValueError(
                    "latitude_column and longitude_column "
                    "are required for spatial_holdout."
                )

            if latitude_column not in X.columns:
                raise ValueError(
                    f"Latitude column not found: "
                    f"{latitude_column}"
                )

            if longitude_column not in X.columns:
                raise ValueError(
                    f"Longitude column not found: "
                    f"{longitude_column}"
                )

            coordinates = X[
                [
                    latitude_column,
                    longitude_column,
                ]
            ].copy()

            if coordinates.isna().any().any():
                raise ValueError(
                    "Spatial columns contain missing values."
                )

            lat_unique = coordinates[
                latitude_column
            ].nunique()

            lon_unique = coordinates[
                longitude_column
            ].nunique()

            lat_q = min(5, lat_unique)
            lon_q = min(5, lon_unique)

            if lat_q < 2 or lon_q < 2:
                raise ValueError(
                    "Not enough spatial variation for "
                    "spatial holdout."
                )

            lat_bins = pd.qcut(
                coordinates[latitude_column],
                q=lat_q,
                labels=False,
                duplicates="drop",
            )

            lon_bins = pd.qcut(
                coordinates[longitude_column],
                q=lon_q,
                labels=False,
                duplicates="drop",
            )

            blocks = (
                lat_bins.astype(str)
                + "_"
                + lon_bins.astype(str)
            )

            unique_blocks = blocks.unique()

            if len(unique_blocks) < 2:
                raise ValueError(
                    "Not enough spatial blocks for "
                    "spatial holdout."
                )

            rng = np.random.default_rng(
                random_state
            )

            shuffled_blocks = rng.permutation(
                unique_blocks
            )

            test_block_count = max(
                1,
                int(
                    np.ceil(
                        len(unique_blocks)
                        * test_size
                    )
                ),
            )

            test_blocks = set(
                shuffled_blocks[
                    :test_block_count
                ]
            )

            test_mask = blocks.isin(
                test_blocks
            )

            train_mask = ~test_mask

            if not train_mask.any():
                raise ValueError(
                    "Spatial training split is empty."
                )

            if not test_mask.any():
                raise ValueError(
                    "Spatial test split is empty."
                )

            return SplitResult(
                X_train=X.loc[train_mask],
                X_test=X.loc[test_mask],
                y_train=y.loc[train_mask],
                y_test=y.loc[test_mask],
            )

        # ======================================================
        # RANDOM HOLDOUT
        # ======================================================

        if strategy == "random_holdout":

            X_train, X_test, y_train, y_test = (
                train_test_split(
                    X,
                    y,
                    test_size=test_size,
                    random_state=random_state,
                )
            )

            return SplitResult(
                X_train=X_train,
                X_test=X_test,
                y_train=y_train,
                y_test=y_test,
            )

        raise ValueError(
            f"Unsupported validation strategy: "
            f"{strategy}"
        )

    # ==========================================================
    # MODEL FACTORY
    # ==========================================================

    @staticmethod
    def _build_model(
        model_name: str,
        task_type: str,
        random_state: int,
    ):

        models = {

            # ---------------- REGRESSION ----------------

            "linear_regression":
                LinearRegression(),

            "random_forest_regressor":
                RandomForestRegressor(
                    n_estimators=200,
                    random_state=random_state,
                    n_jobs=-1,
                ),

            "gradient_boosting_regressor":
                GradientBoostingRegressor(
                    random_state=random_state,
                ),

            "hist_gradient_boosting_regressor":
                HistGradientBoostingRegressor(
                    random_state=random_state,
                ),

            # ------------- CLASSIFICATION ---------------

            "logistic_regression":
                LogisticRegression(
                    max_iter=2000,
                ),

            "random_forest_classifier":
                RandomForestClassifier(
                    n_estimators=200,
                    random_state=random_state,
                    n_jobs=-1,
                ),

            "gradient_boosting_classifier":
                GradientBoostingClassifier(
                    random_state=random_state,
                ),

            "hist_gradient_boosting_classifier":
                HistGradientBoostingClassifier(
                    random_state=random_state,
                ),
        }
        # ---------------- EXTRA TREES ----------------

        models["extra_trees_regressor"] = ExtraTreesRegressor(
            n_estimators=200,
            random_state=random_state,
            n_jobs=-1,
        )

        models["extra_trees_classifier"] = ExtraTreesClassifier(
            n_estimators=200,
            random_state=random_state,
            n_jobs=-1,
        )

        if model_name not in models:
            raise ValueError(
                f"Unsupported model: {model_name}"
            )

        # ------------------------------------------------------
        # Prevent regression/classification mismatch.
        # ------------------------------------------------------

        if (
            task_type == "regression"
            and (
                "classifier" in model_name
                or model_name == "logistic_regression"
            )
        ):
            raise ValueError(
                f"Classification model '{model_name}' "
                f"cannot be used for regression."
            )

        if (
            task_type == "classification"
            and (
                "regressor" in model_name
                or model_name == "linear_regression"
            )
        ):
            raise ValueError(
                f"Regression model '{model_name}' "
                f"cannot be used for classification."
            )

        return models[model_name]

    # ==========================================================
    # PREPROCESSOR
    # ==========================================================

    @staticmethod
    def _build_preprocessor(
        X: pd.DataFrame,
    ):

        numeric_columns = list(
            X.select_dtypes(
                include=["number"]
            ).columns
        )

        categorical_columns = list(
            X.select_dtypes(
                include=[
                    "object",
                    "string",
                    "category",
                    "bool",
                ]
            ).columns
        )

        transformers = []

        # ------------------------------------------------------
        # NUMERIC
        # ------------------------------------------------------

        if numeric_columns:

            numeric_pipeline = Pipeline([
                (
                    "imputer",
                    SimpleImputer(
                        strategy="median"
                    ),
                ),
                (
                    "scaler",
                    StandardScaler(),
                ),
            ])

            transformers.append(
                (
                    "numeric",
                    numeric_pipeline,
                    numeric_columns,
                )
            )

        # ------------------------------------------------------
        # CATEGORICAL
        # ------------------------------------------------------

        if categorical_columns:

            categorical_pipeline = Pipeline([
                (
                    "imputer",
                    SimpleImputer(
                        strategy="most_frequent"
                    ),
                ),
                (
                    "encoder",
                    OneHotEncoder(
                        handle_unknown="ignore",
                    ),
                ),
            ])

            transformers.append(
                (
                    "categorical",
                    categorical_pipeline,
                    categorical_columns,
                )
            )

        if not transformers:
            raise ValueError(
                "No supported feature columns found."
            )

        return ColumnTransformer(
            transformers=transformers,
            remainder="drop",
        )

    # ==========================================================
    # IDENTIFIER REMOVAL
    # ==========================================================

    @staticmethod
    def _remove_identifiers(
        X: pd.DataFrame,
    ) -> pd.DataFrame:

        remove = []

        for column in X.columns:

            name = column.lower().strip()

            if (
                name in {
                    "id",
                    "uuid",
                    "identifier",
                    "key",
                }
                or name.endswith("_id")
                or name.endswith("_uuid")
                or name.endswith("_key")
            ):
                remove.append(column)

        if remove:
            return X.drop(
                columns=remove
            )

        return X

    # ==========================================================
    # EVALUATION
    # ==========================================================

    @staticmethod
    def _evaluate(
        model_name: str,
        task_type: str,
        y_true: pd.Series,
        predictions,
    ) -> ModelEvaluation:

        # ======================================================
        # REGRESSION
        # ======================================================

        if task_type == "regression":

            r2 = float(
                r2_score(
                    y_true,
                    predictions,
                )
            )

            mae = float(
                mean_absolute_error(
                    y_true,
                    predictions,
                )
            )

            rmse = float(
                mean_squared_error(
                    y_true,
                    predictions,
                )
                ** 0.5
            )

            return ModelEvaluation(
                model_name=model_name,
                task=task_type,
                primary_metric=r2,
                metrics={
                    "r2": r2,
                    "mae": mae,
                    "rmse": rmse,
                },
            )

        # ======================================================
        # CLASSIFICATION
        # ======================================================

        if task_type == "classification":

            accuracy = float(
                accuracy_score(
                    y_true,
                    predictions,
                )
            )

            f1 = float(
                f1_score(
                    y_true,
                    predictions,
                    average="weighted",
                    zero_division=0,
                )
            )

            return ModelEvaluation(
                model_name=model_name,
                task=task_type,
                primary_metric=f1,
                metrics={
                    "accuracy": accuracy,
                    "f1_weighted": f1,
                },
            )

        raise ValueError(
            f"Unsupported task type: {task_type}"
        )
