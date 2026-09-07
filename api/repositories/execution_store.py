"""
api/repositories/execution_store.py
------------------------------------
Filesystem-backed store for pipeline execution records.

Stores one JSON file per execution under:
  {store_root}/executions/{execution_id}.json

Thread-safe via a per-instance lock.
Replaceable: callers only depend on ExecutionStore's interface.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ExecutionStore:
    """
    Lightweight execution record store backed by the local filesystem.

    Records are stored as JSON. The store is thread-safe via a per-instance lock.
    It is NOT safe to share across multiple OS processes simultaneously.
    """

    _SUBDIR = "executions"

    def __init__(self, root: Path) -> None:
        self._root = root / self._SUBDIR
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------

    def save(self, execution_id: str, record: dict[str, Any]) -> None:
        """Persist (create or overwrite) an execution record."""
        path = self._path_for(execution_id)
        with self._lock:
            path.write_text(json.dumps(record, default=str), encoding="utf-8")

    def update(self, execution_id: str, updates: dict[str, Any]) -> None:
        """Merge updates into an existing record. Creates record if absent."""
        with self._lock:
            path = self._path_for(execution_id)
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                existing.update(updates)
                path.write_text(json.dumps(existing, default=str), encoding="utf-8")
            else:
                path.write_text(json.dumps(updates, default=str), encoding="utf-8")

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    def get(self, execution_id: str) -> dict[str, Any] | None:
        """Return the execution record or None if not found."""
        path = self._path_for(execution_id)
        with self._lock:
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[dict[str, Any]]:
        """Return all execution records sorted by created_at descending."""
        records = []
        with self._lock:
            for p in self._root.glob("*.json"):
                try:
                    records.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records

    def exists(self, execution_id: str) -> bool:
        with self._lock:
            return self._path_for(execution_id).exists()

    # -----------------------------------------------------------------------
    # Private
    # -----------------------------------------------------------------------

    def _path_for(self, execution_id: str) -> Path:
        # Safety: strip any path separators from execution_id
        safe_id = Path(execution_id).name
        return self._root / f"{safe_id}.json"
