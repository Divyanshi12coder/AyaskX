"""
core/security/audit.py
-----------------------
SecurityAuditLogger — append-only audit log for security events.

Design:
- Interface-first: all callers use SecurityAuditLogger, not the backend.
- Default backend: in-memory + optional JSONL file append.
- Interface designed so PostgreSQL/object-storage backends can be
  substituted later without changing callers.
- Audit entries are NEVER silently discarded.
- The log is append-only: no update or delete operations.

Usage
-----
logger = SecurityAuditLogger()                     # in-memory only
logger = SecurityAuditLogger(log_path="audit.jsonl")  # in-memory + file

logger.record(event)
all_events = logger.events()
exec_events = logger.find_by_execution("exec-001")
artifact_events = logger.find_by_artifact("model:exec-001")
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.security.models import SecurityAuditEvent


class AuditBackend:
    """
    Abstract interface for audit storage.

    Concrete implementations may use in-memory lists, JSONL files,
    databases, or object storage. Callers always go through
    SecurityAuditLogger, never the backend directly.
    """

    def append(self, event: SecurityAuditEvent) -> None:
        raise NotImplementedError

    def all_events(self) -> tuple[SecurityAuditEvent, ...]:
        raise NotImplementedError


class InMemoryAuditBackend(AuditBackend):
    """Thread-safe in-memory audit backend."""

    def __init__(self) -> None:
        self._events: list[SecurityAuditEvent] = []
        self._lock = threading.Lock()

    def append(self, event: SecurityAuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def all_events(self) -> tuple[SecurityAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)


class JsonlAuditBackend(AuditBackend):
    """
    In-memory + append-only JSONL file backend.

    Each line in the file is one JSON object (SecurityAuditEvent.to_dict()).
    The file is never rewritten; only appended.

    Thread-safe via a per-instance lock.
    """

    def __init__(self, log_path: str | Path) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._memory = InMemoryAuditBackend()
        self._lock = threading.Lock()

        # Replay existing file into memory on startup
        if self._path.exists():
            self._replay()

    def _replay(self) -> None:
        """Load existing events from file into memory (startup only)."""
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        event = _event_from_dict(data)
                        self._memory.append(event)
                    except Exception:
                        # Corrupted lines are skipped, not fatal
                        pass
        except OSError:
            pass

    def append(self, event: SecurityAuditEvent) -> None:
        with self._lock:
            self._memory.append(event)
            try:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
                    f.flush()
            except OSError as exc:
                # File write failure is recorded but must not lose the
                # in-memory record. The event is already appended to memory.
                import warnings
                warnings.warn(
                    f"SecurityAuditLogger: could not write to {self._path}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def all_events(self) -> tuple[SecurityAuditEvent, ...]:
        return self._memory.all_events()


class SecurityAuditLogger:
    """
    Append-only audit log for security-relevant events.

    Interface is backend-agnostic; swap backends without changing callers.

    Methods
    -------
    record(event)                    : record a SecurityAuditEvent
    events()                         : all recorded events (immutable tuple)
    find_by_execution(execution_id)  : events for a specific execution
    find_by_artifact(artifact_id)    : events mentioning an artifact_id
    find_by_type(event_type)         : events of a specific SecurityEventType
    """

    def __init__(
        self,
        log_path: str | Path | None = None,
    ) -> None:
        if log_path is not None:
            self._backend: AuditBackend = JsonlAuditBackend(log_path)
        else:
            self._backend = InMemoryAuditBackend()

    def record(self, event: SecurityAuditEvent) -> None:
        """
        Append a SecurityAuditEvent to the log.

        Raises ValueError if event is not a SecurityAuditEvent.
        Never silently discards events.
        """
        if not isinstance(event, SecurityAuditEvent):
            raise ValueError(
                f"Expected SecurityAuditEvent, got {type(event).__name__}"
            )
        self._backend.append(event)

    def events(self) -> tuple[SecurityAuditEvent, ...]:
        """Return all recorded events in insertion order."""
        return self._backend.all_events()

    def find_by_execution(
        self,
        execution_id: str,
    ) -> tuple[SecurityAuditEvent, ...]:
        """Return all events for a specific execution_id."""
        return tuple(
            e for e in self._backend.all_events()
            if e.execution_id == execution_id
        )

    def find_by_artifact(
        self,
        artifact_id: str,
    ) -> tuple[SecurityAuditEvent, ...]:
        """Return all events whose metadata contains the given artifact_id."""
        return tuple(
            e for e in self._backend.all_events()
            if e.metadata.get("artifact_id") == artifact_id
            or artifact_id in e.action
            or artifact_id in e.reason
        )

    def find_by_type(
        self,
        event_type: "SecurityEventType",  # noqa: F821
    ) -> tuple[SecurityAuditEvent, ...]:
        """Return all events of a specific SecurityEventType."""
        return tuple(
            e for e in self._backend.all_events()
            if e.event_type == event_type
        )

    def count(self) -> int:
        """Return total number of recorded events."""
        return len(self._backend.all_events())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event_from_dict(data: dict[str, Any]) -> SecurityAuditEvent:
    """Deserialize a SecurityAuditEvent from a dict (used for JSONL replay)."""
    from core.security.models import SecurityEventType, SecuritySeverity

    return SecurityAuditEvent(
        event_id=data["event_id"],
        event_type=SecurityEventType(data["event_type"]),
        execution_id=data["execution_id"],
        component=data["component"],
        severity=SecuritySeverity(data["severity"]),
        timestamp=datetime.fromisoformat(data["timestamp"]),
        action=data["action"],
        reason=data["reason"],
        metadata=data.get("metadata", {}),
    )
