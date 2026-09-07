"""
api/repositories/dataset_store.py
-----------------------------------
Filesystem-backed dataset registry.

Stores dataset metadata under {store_root}/datasets/{dataset_id}.json.
Raw uploaded files are stored separately in upload_tmp_root.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class DatasetStore:
    _SUBDIR = "datasets"

    def __init__(self, root: Path) -> None:
        self._root = root / self._SUBDIR
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def save(self, dataset_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            self._path_for(dataset_id).write_text(
                json.dumps(record, default=str), encoding="utf-8"
            )

    def get(self, dataset_id: str) -> dict[str, Any] | None:
        with self._lock:
            p = self._path_for(dataset_id)
            if not p.exists():
                return None
            return json.loads(p.read_text(encoding="utf-8"))

    def list_all(self) -> list[dict[str, Any]]:
        records = []
        with self._lock:
            for p in self._root.glob("*.json"):
                try:
                    records.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
        records.sort(key=lambda r: r.get("registered_at", ""), reverse=True)
        return records

    def exists(self, dataset_id: str) -> bool:
        with self._lock:
            return self._path_for(dataset_id).exists()

    def _path_for(self, dataset_id: str) -> Path:
        safe_id = Path(dataset_id).name
        return self._root / f"{safe_id}.json"
