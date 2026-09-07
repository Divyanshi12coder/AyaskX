from dataclasses import dataclass

import numpy as np
import pandas as pd

from sklearn.model_selection import (
    GroupShuffleSplit,
    StratifiedShuffleSplit,
    train_test_split,
)


@dataclass(frozen=True)
class SplitResult:
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series


class ValidationSplitter:

    def split(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        strategy: str = "random_holdout",
        test_size: float = 0.2,
        random_state: int = 42,
        group_column: str | None = None,
        time_column: str | None = None,
        latitude_column: str | None = None,
        longitude_column: str | None = None,
    ) -> SplitResult:

        if len(X) != len(y):
            raise ValueError(
                "X and y must contain the same number of rows."
            )

        if len(X) < 4:
            raise ValueError(
                "Dataset is too small for validation splitting."
            )

        if not 0 < test_size < 1:
            raise ValueError(
                "test_size must be between 0 and 1."
            )

        # ----------------------------------------------------------
        # RANDOM
        # ----------------------------------------------------------

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

        # ----------------------------------------------------------
        # STRATIFIED
        # ----------------------------------------------------------

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

        # ----------------------------------------------------------
        # GROUP
        # ----------------------------------------------------------

        if strategy == "group_holdout":

            if group_column is None:
                raise ValueError(
                    "group_column is required "
                    "for group_holdout."
                )

            if group_column not in X.columns:
                raise ValueError(
                    f"Group column not found: {group_column}"
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

        # ----------------------------------------------------------
        # TEMPORAL
        # ----------------------------------------------------------

        if strategy == "temporal_holdout":

            if time_column is None:
                raise ValueError(
                    "time_column is required "
                    "for temporal_holdout."
                )

            if time_column not in X.columns:
                raise ValueError(
                    f"Time column not found: {time_column}"
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

        # ----------------------------------------------------------
        # SPATIAL
        # ----------------------------------------------------------

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

            # ------------------------------------------------------
            # Spatial blocking
            #
            # Instead of randomly splitting nearby points,
            # divide the geographic space into coarse cells.
            # Entire cells are assigned to either train or test.
            # ------------------------------------------------------

            lat_bins = pd.qcut(
                coordinates[latitude_column],
                q=min(
                    5,
                    coordinates[latitude_column].nunique(),
                ),
                labels=False,
                duplicates="drop",
            )

            lon_bins = pd.qcut(
                coordinates[longitude_column],
                q=min(
                    5,
                    coordinates[longitude_column].nunique(),
                ),
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

        raise ValueError(
            f"Unsupported validation strategy: "
            f"{strategy}"
        )