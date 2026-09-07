from core.pipeline.checkpoints import (
    CheckpointManager,
)


def test_creates_checkpoint(tmp_path):

    manager = CheckpointManager(
        tmp_path
    )

    checkpoint = manager.create(
        execution_id="exec-1",
        node_id="ingestion",
        artifact={
            "rows": 100,
            "columns": 5,
        },
        node_version="1.0",
    )

    assert checkpoint.checkpoint_id
    assert checkpoint.execution_id == "exec-1"
    assert checkpoint.node_id == "ingestion"
    assert checkpoint.validation_status == "passed"
    assert checkpoint.data_hash


def test_checkpoint_can_be_restored(tmp_path):

    manager = CheckpointManager(
        tmp_path
    )

    artifact = {
        "rows": 100,
        "status": "valid",
    }

    checkpoint = manager.create(
        execution_id="exec-1",
        node_id="validation",
        artifact=artifact,
    )

    restored = manager.restore(
        checkpoint.checkpoint_id
    )

    assert restored == artifact


def test_last_known_good(tmp_path):

    manager = CheckpointManager(
        tmp_path
    )

    first = manager.create(
        execution_id="exec-1",
        node_id="ingestion",
        artifact={"step": 1},
    )

    manager.create(
        execution_id="exec-1",
        node_id="validation",
        artifact={"step": 2},
        validation_status="failed",
    )

    latest_good = (
        manager.last_known_good(
            execution_id="exec-1"
        )
    )

    assert latest_good is not None
    assert (
        latest_good.checkpoint_id
        == first.checkpoint_id
    )


def test_checkpoint_hash_is_deterministic(
    tmp_path,
):

    manager = CheckpointManager(
        tmp_path
    )

    first = manager.create(
        execution_id="exec-1",
        node_id="node-a",
        artifact={
            "a": 1,
            "b": 2,
        },
    )

    second = manager.create(
        execution_id="exec-1",
        node_id="node-b",
        artifact={
            "a": 1,
            "b": 2,
        },
    )

    assert (
        first.data_hash
        == second.data_hash
    )


def test_missing_checkpoint_raises(tmp_path):

    manager = CheckpointManager(
        tmp_path
    )

    try:
        manager.restore("does-not-exist")
        assert False
    except KeyError:
        assert True