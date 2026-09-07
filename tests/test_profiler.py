import pandas as pd

from eda.profiler import DatasetProfiler


def test_profiler_detects_dataset_structure():

    df = pd.DataFrame({
        "mine_id": ["M1", "M2", "M3", "M4"],
        "latitude": [21.1, 21.2, 21.3, 21.4],
        "grade": [30.2, 31.4, 28.7, 35.1],
        "production": [100, 120, 90, 140],
        "event_time": [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-04",
        ],
    })

    profiler = DatasetProfiler()

    profile = profiler.profile(df)

    assert profile.rows == 4
    assert profile.column_count == 5

    assert "grade" in profile.numeric_columns
    assert "production" in profile.numeric_columns

    assert "latitude" in profile.spatial_candidates
    assert "event_time" in profile.datetime_candidates

    assert "mine_id" in profile.identifier_candidates