from pathlib import Path

from data.ingestion.friend_adapter import FriendDatasetAdapter


def test_friend_dataset_discovery():

    root = Path("source_friend_v1")

    adapter = FriendDatasetAdapter(root)

    datasets = adapter.discover()

    assert len(datasets) > 0

    for dataset in datasets:
        assert dataset.rows > 0
        assert dataset.columns > 0
        assert dataset.schema_hash