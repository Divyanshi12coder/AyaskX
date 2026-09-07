from pathlib import Path

from data.ingestion.friend_adapter import FriendDatasetAdapter
from data.registry.registry import DatasetRegistry


def test_registry_registers_datasets():

    adapter = FriendDatasetAdapter(
        Path("source_friend_v1")
    )

    datasets = adapter.discover()

    registry = DatasetRegistry()

    for dataset in datasets:
        registry.register(dataset)

    assert len(registry) == len(datasets)

    first = datasets[0]

    registered = registry.get(first.name)

    assert registered.name == first.name
    assert registered.rows == first.rows
    assert registered.columns == first.columns