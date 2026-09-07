import pandas as pd

from core.validation.strategy import (
    ValidationStrategySelector,
)


def test_selects_spatial_validation():

    df = pd.DataFrame({
        "latitude": [21.1, 21.2, 21.3, 21.4],
        "longitude": [80.1, 80.2, 80.3, 80.4],
        "ndvi": [0.2, 0.3, 0.4, 0.5],
        "prospectivity_label": [0, 1, 0, 1],
    })

    result = ValidationStrategySelector().select(
        df,
        target="prospectivity_label",
    )

    assert result.strategy == "spatial_holdout"
    assert result.primary_column == "latitude"
    assert result.secondary_column == "longitude"


def test_selects_temporal_validation():

    df = pd.DataFrame({
        "event_time": [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-04",
        ],
        "rainfall": [10, 20, 15, 5],
        "production": [100, 120, 110, 130],
    })

    result = ValidationStrategySelector().select(
        df,
        target="production",
    )

    assert result.strategy == "temporal_holdout"
    assert result.primary_column == "event_time"


def test_selects_group_validation():

    df = pd.DataFrame({
        "mine_id": [
            "M1",
            "M1",
            "M2",
            "M2",
        ],
        "grade": [30, 31, 35, 34],
        "production": [100, 110, 120, 125],
    })

    result = ValidationStrategySelector().select(
        df,
        target="production",
    )

    assert result.strategy == "group_holdout"
    assert result.primary_column == "mine_id"


def test_selects_stratified_validation():

    df = pd.DataFrame({
        "grade": [30, 31, 35, 34],
        "risk": [0, 1, 0, 1],
    })

    result = ValidationStrategySelector().select(
        df,
        target="risk",
    )

    assert result.strategy == "stratified_holdout"


def test_selects_random_fallback():

    df = pd.DataFrame({
        "feature_a": [1.0, 2.0, 3.0, 4.0],
        "feature_b": [4.0, 3.0, 2.0, 1.0],
        "target": [10.0, 20.0, 30.0, 40.0],
    })

    result = ValidationStrategySelector().select(
        df,
        target="target",
    )

    assert result.strategy == "random_holdout"