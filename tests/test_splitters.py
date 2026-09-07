import pandas as pd

from core.models.splitters import (
    ValidationSplitter,
)


def test_random_split():

    X = pd.DataFrame({
        "grade": range(20),
    })

    y = pd.Series(range(20))

    result = ValidationSplitter().split(
        X,
        y,
        strategy="random_holdout",
    )

    assert len(result.X_train) == 16
    assert len(result.X_test) == 4


def test_stratified_split():

    X = pd.DataFrame({
        "grade": range(20),
    })

    y = pd.Series(
        [0, 1] * 10
    )

    result = ValidationSplitter().split(
        X,
        y,
        strategy="stratified_holdout",
    )

    assert len(result.X_train) == 16
    assert len(result.X_test) == 4

    assert set(
        result.y_train.unique()
    ) == {0, 1}

    assert set(
        result.y_test.unique()
    ) == {0, 1}


def test_group_split():

    X = pd.DataFrame({
        "mine_id": [
            "M1", "M1", "M1",
            "M2", "M2", "M2",
            "M3", "M3", "M3",
            "M4", "M4", "M4",
        ],
        "grade": range(12),
    })

    y = pd.Series(range(12))

    result = ValidationSplitter().split(
        X,
        y,
        strategy="group_holdout",
        group_column="mine_id",
    )

    train_groups = set(
        result.X_train["mine_id"]
    )

    test_groups = set(
        result.X_test["mine_id"]
    )

    assert train_groups.isdisjoint(
        test_groups
    )


def test_temporal_split():

    X = pd.DataFrame({
        "event_time": pd.date_range(
            "2026-01-01",
            periods=20,
            freq="D",
        ),
        "grade": range(20),
    })

    y = pd.Series(range(20))

    result = ValidationSplitter().split(
        X,
        y,
        strategy="temporal_holdout",
        time_column="event_time",
    )

    assert len(result.X_train) == 16
    assert len(result.X_test) == 4

    assert (
        result.X_train["event_time"].max()
        <
        result.X_test["event_time"].min()
    )


def test_spatial_split():

    X = pd.DataFrame({
        "latitude": [
            20, 20, 21, 21,
            22, 22, 23, 23,
            24, 24,
        ],
        "longitude": [
            75, 76, 75, 76,
            77, 78, 77, 78,
            79, 80,
        ],
        "grade": range(10),
    })

    y = pd.Series(range(10))

    result = ValidationSplitter().split(
        X,
        y,
        strategy="spatial_holdout",
        latitude_column="latitude",
        longitude_column="longitude",
    )

    assert len(result.X_train) > 0
    assert len(result.X_test) > 0


def test_invalid_group_strategy():

    X = pd.DataFrame({
        "grade": range(10),
    })

    y = pd.Series(range(10))

    try:

        ValidationSplitter().split(
            X,
            y,
            strategy="group_holdout",
        )

        assert False

    except ValueError:

        assert True