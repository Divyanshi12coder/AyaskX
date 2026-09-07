import pandas as pd

from core.feature_roles.detector import (
    FeatureRoleDetector,
)


def test_detects_feature_roles():

    df = pd.DataFrame({
        "mine_id": ["M1", "M2", "M3"],
        "latitude": [21.1, 21.2, 21.3],
        "longitude": [80.1, 80.2, 80.3],
        "production_date": [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
        ],
        "grade": [30.1, 31.2, 29.8],
        "mine_type": [
            "open",
            "open",
            "underground",
        ],
        "active": [True, False, True],
        "description": [
            "short text",
            "another short text",
            "third short text",
        ],
        "production": [100, 120, 90],
    })

    detector = FeatureRoleDetector()

    report = detector.detect(
        df,
        target="production",
    )

    assert "production" in report.target_columns

    assert "mine_id" in report.identifier_columns

    assert "latitude" in report.spatial_columns
    assert "longitude" in report.spatial_columns

    assert "production_date" in report.temporal_columns

    assert "grade" in report.numeric_columns

    assert "mine_type" in report.categorical_columns

    assert "active" in report.boolean_columns


def test_detects_string_datetime():

    df = pd.DataFrame({
        "event_time": [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
        ],
        "value": [10, 20, 30],
    })

    report = FeatureRoleDetector().detect(df)

    assert "event_time" in report.temporal_columns
    assert "value" in report.numeric_columns


def test_downtime_hours_is_numeric_not_datetime():

    df = pd.DataFrame({
        "downtime_hours": [1.5, 2.0, 0.5],
    })

    report = FeatureRoleDetector().detect(df)

    assert "downtime_hours" in report.numeric_columns
    assert "downtime_hours" not in report.temporal_columns