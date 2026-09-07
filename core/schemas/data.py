from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class ProvenanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provenance_id: str
    source_file: str
    source_record_id: str | None = None
    ingestion_run_id: str
    transformation_version: str
    ingested_at: datetime

class DatasetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str
    dataset_name: str
    source_version: str
    created_at: datetime
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    schema_hash: str
    file_hash: str
    metadata: dict[str, Any] = {}
