import pandas as pd

from core.preprocessing.recommender import (
    PreprocessingRecommender,
)


def test_recommends_numeric_processing():

    df = pd.DataFrame({
        "grade": [30.0, None, 35.0, 40.0],
        "rainfall": [10.0, 20.0, 15.0, 5.0],
        "production": [100, 120, 110, 130],
    })

    plan = PreprocessingRecommender().recommend(
        df,
        target="production",
    )

    assert "grade" in plan.numeric_columns
    assert "rainfall" in plan.numeric_columns

    grade = next(
        x
        for x in plan.recommendations
        if x.column == "grade"
    )

    assert "median_imputation" in grade.actions
    assert "scale_if_model_requires_it" in grade.actions


def test_recommends_categorical_encoding():

    df = pd.DataFrame({
        "mine_type": [
            "open",
            "open",
            "underground",
        ],
        "production": [100, 120, 110],
    })

    plan = PreprocessingRecommender().recommend(
        df,
        target="production",
    )

    assert "mine_type" in plan.categorical_columns

    item = next(
        x
        for x in plan.recommendations
        if x.column == "mine_type"
    )

    assert (
        "one_hot_or_ordinal_encoding"
        in item.actions
    )


def test_identifier_is_not_default_feature():

    df = pd.DataFrame({
        "mine_id": ["M1", "M2", "M3"],
        "grade": [30.0, 31.0, 32.0],
        "production": [100, 120, 110],
    })

    plan = PreprocessingRecommender().recommend(
        df,
        target="production",
    )

    assert "mine_id" in plan.identifier_columns

    item = next(
        x
        for x in plan.recommendations
        if x.column == "mine_id"
    )

    assert (
        "exclude_from_default_features"
        in item.actions
    )


def test_temporal_feature_gets_date_features():

    df = pd.DataFrame({
        "event_time": [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
        ],
        "production": [100, 120, 110],
    })

    plan = PreprocessingRecommender().recommend(
        df,
        target="production",
    )

    assert (
        "event_time"
        in plan.temporal_columns
    )

    item = next(
        x
        for x in plan.recommendations
        if x.column == "event_time"
    )

    assert "parse_datetime" in item.actions
    assert "extract_year" in item.actions