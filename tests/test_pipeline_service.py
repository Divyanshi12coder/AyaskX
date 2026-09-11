from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from api.services.pipeline_service import PipelineService


class _Store:
    def __init__(self):
        self.records: dict[str, dict] = {}

    def save(self, execution_id: str, record: dict) -> None:
        self.records[execution_id] = record

    def update(self, execution_id: str, values: dict) -> None:
        self.records[execution_id].update(values)

    def get(self, execution_id: str):
        return self.records.get(execution_id)

    def list_all(self):
        return list(self.records.values())


@dataclass
class _Checkpoint:
    checkpoint_id: str
    execution_id: str
    node_id: str = "characterize"
    created_at: str = "2026-09-08T00:00:00+00:00"
    validation_status: str = "passed"
    artifact_path: str | None = None
    data_hash: str = "hash"


class _CheckpointManager:
    def __init__(self):
        self._checkpoints = {}

    def list(self):
        return tuple(self._checkpoints.values())


class _Orchestrator:
    def __init__(self):
        self.checkpoint_manager = _CheckpointManager()
        self.received_execution_id: str | None = None

    def run(self, _df, *, execution_id: str, **_kwargs):
        self.received_execution_id = execution_id
        self.checkpoint_manager._checkpoints["checkpoint-1"] = _Checkpoint(
            checkpoint_id="checkpoint-1", execution_id=execution_id
        )
        return _Result(execution_id)


class _Result:
    pipeline_execution = None
    characterization = None
    feature_roles = None
    leakage_report = None
    preprocessing_plan = None
    candidate_report = None
    training_result = None
    validation_strategy = None
    success = True

    def __init__(self, execution_id: str):
        self.execution_id = execution_id

    def to_summary(self):
        return {"message": "ok", "warnings": []}


def test_pipeline_service_propagates_api_execution_id_to_core_and_checkpoints():
    store = _Store()
    orchestrator = _Orchestrator()
    service = PipelineService(orchestrator=orchestrator, execution_store=store)

    execution_id = "api-execution-1"
    store.save(execution_id, {"execution_id": execution_id, "status": "queued"})
    service._run_in_background(
        execution_id,
        pd.DataFrame({"feature": [1], "target": [2]}),
        "dataset.csv",
        "target",
        "regression",
        None,
    )

    assert orchestrator.received_execution_id == execution_id
    assert store.get(execution_id)["checkpoints"] == [
        {
            "checkpoint_id": "checkpoint-1",
            "execution_id": execution_id,
            "node_id": "characterize",
            "created_at": "2026-09-08T00:00:00+00:00",
            "validation_status": "passed",
            "artifact_path": None,
            "data_hash": "hash",
        }
    ]
