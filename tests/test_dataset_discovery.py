from pathlib import Path

import pandas as pd

from core.datasets.discovery import DatasetDiscovery


def test_discovers_csv_datasets(tmp_path: Path):

    data_dir = tmp_path / "datasets"
    data_dir.mkdir()

    df = pd.DataFrame({
        "mine_id": ["M1", "M2"],
        "grade": [30.0, 35.0],
        "production": [100, 120],
    })

    df.to_csv(
        data_dir / "sample.csv",
        index=False,
    )

    result = DatasetDiscovery().discover(
        data_dir
    )

    assert len(result.datasets) == 1

    dataset = result.datasets[0]

    assert dataset.rows == 2
    assert dataset.columns == 3

    assert dataset.column_names == (
        "mine_id",
        "grade",
        "production",
    )


def test_discovers_nested_csv_files(tmp_path: Path):

    data_dir = tmp_path / "datasets"
    nested = data_dir / "nested"
    nested.mkdir(parents=True)

    pd.DataFrame({
        "a": [1, 2, 3]
    }).to_csv(
        nested / "data.csv",
        index=False,
    )

    result = DatasetDiscovery().discover(
        data_dir
    )

    assert len(result.datasets) == 1

    assert result.datasets[0].rows == 3


def test_non_csv_files_are_ignored(tmp_path: Path):

    data_dir = tmp_path / "datasets"
    data_dir.mkdir()

    (data_dir / "notes.txt").write_text(
        "not a dataset"
    )

    pd.DataFrame({
        "value": [1, 2]
    }).to_csv(
        data_dir / "data.csv",
        index=False,
    )

    result = DatasetDiscovery().discover(
        data_dir
    )

    assert len(result.datasets) == 1


def test_missing_directory_raises(tmp_path: Path):

    missing = tmp_path / "does_not_exist"

    try:
        DatasetDiscovery().discover(missing)
        assert False
    except FileNotFoundError:
        pass