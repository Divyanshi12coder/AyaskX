"""
tests/test_security_audit.py
-----------------------------
Tests for SecurityAuditEvent, SecurityAuditLogger (in-memory + JSONL backends).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.security.audit import SecurityAuditLogger
from core.security.models import (
    SecurityAuditEvent,
    SecurityEventType,
    SecuritySeverity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type=SecurityEventType.INTEGRITY_CHECK_PASSED,
    execution_id="exec-001",
    severity=SecuritySeverity.INFO,
    component="TestComponent",
    action="test action",
    reason="test reason",
    metadata=None,
) -> SecurityAuditEvent:
    return SecurityAuditEvent(
        event_type=event_type,
        execution_id=execution_id,
        component=component,
        severity=severity,
        action=action,
        reason=reason,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# SecurityAuditEvent
# ---------------------------------------------------------------------------

class TestSecurityAuditEvent:
    def test_is_immutable(self):
        evt = _make_event()
        with pytest.raises((FrozenInstanceError, AttributeError)):
            evt.action = "modified"  # type: ignore[misc]

    def test_has_unique_event_id(self):
        e1 = _make_event()
        e2 = _make_event()
        assert e1.event_id != e2.event_id

    def test_to_dict_is_json_serializable(self):
        evt = _make_event(metadata={"key": "value", "num": 42})
        d = evt.to_dict()
        assert json.dumps(d)  # must not raise
        assert d["event_type"] == SecurityEventType.INTEGRITY_CHECK_PASSED.value
        assert d["severity"] == SecuritySeverity.INFO.value
        assert d["metadata"]["key"] == "value"

    def test_timestamp_is_utc(self):
        evt = _make_event()
        assert evt.timestamp.tzinfo is not None

    def test_event_types_are_strings(self):
        for et in SecurityEventType:
            assert isinstance(et.value, str)

    def test_all_severity_values_are_strings(self):
        for s in SecuritySeverity:
            assert isinstance(s.value, str)


# ---------------------------------------------------------------------------
# SecurityAuditLogger — in-memory
# ---------------------------------------------------------------------------

class TestSecurityAuditLoggerMemory:
    def test_starts_empty(self):
        logger = SecurityAuditLogger()
        assert logger.count() == 0

    def test_record_increases_count(self):
        logger = SecurityAuditLogger()
        logger.record(_make_event())
        assert logger.count() == 1

    def test_record_preserves_insertion_order(self):
        logger = SecurityAuditLogger()
        e1 = _make_event(action="first")
        e2 = _make_event(action="second")
        logger.record(e1)
        logger.record(e2)
        events = logger.events()
        assert events[0].action == "first"
        assert events[1].action == "second"

    def test_events_returns_immutable_tuple(self):
        logger = SecurityAuditLogger()
        logger.record(_make_event())
        result = logger.events()
        assert isinstance(result, tuple)

    def test_find_by_execution(self):
        logger = SecurityAuditLogger()
        logger.record(_make_event(execution_id="exec-A"))
        logger.record(_make_event(execution_id="exec-B"))
        logger.record(_make_event(execution_id="exec-A"))
        found = logger.find_by_execution("exec-A")
        assert len(found) == 2

    def test_find_by_execution_returns_empty_when_none(self):
        logger = SecurityAuditLogger()
        logger.record(_make_event(execution_id="exec-A"))
        found = logger.find_by_execution("exec-Z")
        assert len(found) == 0

    def test_find_by_type(self):
        logger = SecurityAuditLogger()
        logger.record(_make_event(event_type=SecurityEventType.INTEGRITY_CHECK_PASSED))
        logger.record(_make_event(event_type=SecurityEventType.INTEGRITY_CHECK_FAILED))
        logger.record(_make_event(event_type=SecurityEventType.INTEGRITY_CHECK_PASSED))
        found = logger.find_by_type(SecurityEventType.INTEGRITY_CHECK_PASSED)
        assert len(found) == 2

    def test_find_by_artifact_matches_metadata(self):
        logger = SecurityAuditLogger()
        logger.record(_make_event(
            action="check artifact",
            metadata={"artifact_id": "my_model:exec-001"},
        ))
        logger.record(_make_event(action="unrelated"))
        found = logger.find_by_artifact("my_model:exec-001")
        assert len(found) >= 1

    def test_record_rejects_wrong_type(self):
        logger = SecurityAuditLogger()
        with pytest.raises(ValueError):
            logger.record("not an event")  # type: ignore[arg-type]

    def test_multiple_records_all_stored(self):
        logger = SecurityAuditLogger()
        for i in range(20):
            logger.record(_make_event(execution_id=f"exec-{i}"))
        assert logger.count() == 20


# ---------------------------------------------------------------------------
# SecurityAuditLogger — JSONL backend
# ---------------------------------------------------------------------------

class TestSecurityAuditLoggerJsonl:
    def test_events_written_to_file(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        logger = SecurityAuditLogger(log_path=log)
        logger.record(_make_event(action="file-event"))
        assert log.exists()
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["action"] == "file-event"

    def test_multiple_events_each_on_own_line(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        logger = SecurityAuditLogger(log_path=log)
        logger.record(_make_event(action="ev1"))
        logger.record(_make_event(action="ev2"))
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_replay_from_file_on_new_logger(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        # First logger writes events
        logger1 = SecurityAuditLogger(log_path=log)
        logger1.record(_make_event(action="persisted-event"))
        # Second logger replays from same file
        logger2 = SecurityAuditLogger(log_path=log)
        assert logger2.count() == 1
        assert logger2.events()[0].action == "persisted-event"

    def test_file_is_append_only(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        logger = SecurityAuditLogger(log_path=log)
        logger.record(_make_event(action="first"))
        # Create new logger pointing to same file
        logger2 = SecurityAuditLogger(log_path=log)
        logger2.record(_make_event(action="second"))
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_jsonl_events_are_fully_serialized(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        logger = SecurityAuditLogger(log_path=log)
        evt = _make_event(
            event_type=SecurityEventType.ARTIFACT_QUARANTINED,
            severity=SecuritySeverity.HIGH,
            metadata={"artifact_id": "m:e1", "path": "/some/path"},
        )
        logger.record(evt)
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        data = json.loads(lines[0])
        assert data["event_type"] == "artifact_quarantined"
        assert data["severity"] == "high"
        assert data["metadata"]["artifact_id"] == "m:e1"
