import pandas as pd

from core.leakage.detector import LeakageDetector


def test_detects_future_columns():

    df = pd.DataFrame({
        "rainfall_mm": [10, 20, 15],
        "production": [100, 120, 110],
        "actual_production": [98, 119, 108],
        "production_next_shift": [105, 130, 115],
    })

    report = LeakageDetector().analyze(
        df,
        target="production",
    )

    assert "actual_production" in report.risky_features
    assert "production_next_shift" in report.risky_features


def test_keeps_normal_features_safe():

    df = pd.DataFrame({
        "rainfall_mm": [10, 20, 15],
        "soil_wetness": [0.2, 0.5, 0.3],
        "production": [100, 120, 110],
    })

    report = LeakageDetector().analyze(
        df,
        target="production",
    )

    assert "rainfall_mm" in report.safe_features
    assert "soil_wetness" in report.safe_features
    assert "production" not in report.safe_features