import pandas as pd

from core.datasets.characterization import (
    DatasetCharacterizer,
)


def test_characterizes_basic_dataset():

    df = pd.DataFrame({
        "mine_id": [
            "M1",
            "M1",
            "M2",
            "M2",
        ],
        "latitude": [
            21.1,
            21.2,
            21.3,
            21.4,
        ],
        "longitude": [
            85.1,
            85.2,
            85.3,
            85.4,
        ],
        "grade": [
            30.0,
            31.0,
            35.0,
            34.0,
        ],
        "production": [
            100,
            110,
            120,
            125,
        ],
    })

    result = DatasetCharacterizer().characterize(
        df,
        path="ml_ready/production_train.csv",
    )

    assert result.rows == 4
    assert result.columns == 5

    assert "grade" in result.numeric_columns
    assert "production" in result.numeric_columns

    assert "latitude" in result.spatial_columns
    assert "longitude" in result.spatial_columns

    assert "mine_id" in result.group_columns

    assert "production" in result.target_candidates

    assert result.dataset_role == "ml_ready"


def test_detects_datetime():

    df = pd.DataFrame({
        "event_time": [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-04",
        ],
        "production": [
            100,
            110,
            120,
            130,
        ],
    })

    result = DatasetCharacterizer().characterize(
        df,
        path="production.csv",
    )

    assert "event_time" in result.temporal_columns
    assert "event_time" in result.datetime_columns


def test_detects_missing_values():

    df = pd.DataFrame({
        "grade": [
            30.0,
            None,
            35.0,
            40.0,
        ],
        "production": [
            100,
            110,
            None,
            140,
        ],
    })

    result = DatasetCharacterizer().characterize(
        df
    )

    assert "grade" in result.missing_columns
    assert "production" in result.missing_columns


def test_detects_constant_columns():

    df = pd.DataFrame({
        "source": [
            "synthetic",
            "synthetic",
            "synthetic",
            "synthetic",
        ],
        "grade": [
            30,
            31,
            32,
            33,
        ],
    })

    result = DatasetCharacterizer().characterize(
        df
    )

    assert "source" in result.constant_columns


def test_detects_metadata_dataset():

    df = pd.DataFrame({
        "dataset_id": [
            "D1",
            "D2",
        ],
        "description": [
            "dataset one",
            "dataset two",
        ],
        "source": [
            "synthetic",
            "synthetic",
        ],
    })

    result = DatasetCharacterizer().characterize(
        df,
        path="metadata/dataset_manifest.csv",
    )

    assert result.dataset_role == "metadata"