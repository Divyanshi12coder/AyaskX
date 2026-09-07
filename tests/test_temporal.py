import pandas as pd

from data.validation.temporal import TemporalValidator


def test_invalid_datetime():

    df = pd.DataFrame({
        "timestamp": [
            "2026-01-01",
            "invalid-date",
        ]
    })

    validator = TemporalValidator()

    issues = validator.validate_datetime(
        df,
        "timestamp",
    )

    assert len(issues) == 1
    assert issues[0].code == "INVALID_DATETIME"


def test_future_information():

    df = pd.DataFrame({
        "prediction_time": pd.to_datetime([
            "2026-01-01",
            "2026-01-02",
        ]),
        "future_equipment_state": pd.to_datetime([
            "2026-01-02",
            "2026-01-01",
        ]),
    })

    validator = TemporalValidator()

    issues = validator.detect_future_columns(
        df,
        "prediction_time",
    )

    assert len(issues) == 1
    assert issues[0].code == "FUTURE_INFORMATION"


def test_monotonic_time():

    df = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01",
            "2026-01-03",
            "2026-01-02",
        ])
    })

    validator = TemporalValidator()

    issues = validator.check_monotonic_time(
        df,
        "timestamp",
    )

    assert len(issues) == 1
    assert issues[0].code == "NON_MONOTONIC_TIME"