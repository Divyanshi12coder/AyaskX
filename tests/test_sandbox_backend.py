"""
tests/test_sandbox_backend.py
------------------------------
Tests for SandboxBackend abstraction (Phase J hardening).

Verifies:
- SandboxBackend interface is defined.
- InProcessBackend executes handlers in-process.
- InProcessBackend explicitly reports execution_mode='in_process'.
- SandboxResult.execution_mode is populated correctly.
- SandboxExecutor accepts a backend parameter.
- Existing SandboxExecutor behavior is fully preserved (backward-compatible).
- No false claims of OS isolation from InProcessBackend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.repair.sandbox import (
    InProcessBackend,
    SandboxBackend,
    SandboxExecutor,
    SandboxResult,
    SandboxStatus,
    StepExecutionRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_step(
    step_index: int = 0,
    action_type: str = "RERUN_NODE",
    target_node: str = "training",
    requires_validation: bool = False,
) -> MagicMock:
    step = MagicMock()
    step.step_index = step_index
    step.action_type = action_type
    step.target_node = target_node
    step.requires_validation = requires_validation
    return step


def _make_plan(
    execution_id: str = "exec-001",
    hypothesis_category: str = "MISSING_ARTIFACT",
    steps=None,
) -> MagicMock:
    plan = MagicMock()
    plan.execution_id = execution_id
    plan.hypothesis_category = hypothesis_category
    plan.steps = steps or []
    return plan


# ---------------------------------------------------------------------------
# SandboxBackend interface
# ---------------------------------------------------------------------------

class TestSandboxBackendInterface:
    def test_abstract_execution_mode_raises(self):
        backend = SandboxBackend()
        with pytest.raises(NotImplementedError):
            _ = backend.execution_mode

    def test_abstract_execute_step_raises(self):
        backend = SandboxBackend()
        with pytest.raises(NotImplementedError):
            backend.execute_step(None, lambda s, c: {}, None)


# ---------------------------------------------------------------------------
# InProcessBackend
# ---------------------------------------------------------------------------

class TestInProcessBackend:
    def test_execution_mode_is_in_process(self):
        backend = InProcessBackend()
        assert backend.execution_mode == "in_process"

    def test_is_sandbox_backend(self):
        assert isinstance(InProcessBackend(), SandboxBackend)

    def test_executes_handler_and_returns_result(self):
        backend = InProcessBackend()
        step = _make_step()
        handler = lambda s, c: {"success": True, "message": "done"}
        result = backend.execute_step(step, handler, context=None)
        assert result["success"] is True
        assert result["message"] == "done"

    def test_passes_step_and_context_to_handler(self):
        backend = InProcessBackend()
        received = {}

        def handler(step, context):
            received["step"] = step
            received["context"] = context
            return {"success": True, "message": "ok"}

        step = _make_step()
        ctx = {"foo": "bar"}
        backend.execute_step(step, handler, context=ctx)
        assert received["step"] is step
        assert received["context"] is ctx

    def test_does_not_claim_os_isolation(self):
        backend = InProcessBackend()
        assert backend.execution_mode != "isolated"
        assert backend.execution_mode != "subprocess"
        assert backend.execution_mode != "docker"
        assert "process" in backend.execution_mode.lower()


# ---------------------------------------------------------------------------
# SandboxExecutor — backend parameter
# ---------------------------------------------------------------------------

class TestSandboxExecutorBackend:
    def test_default_backend_is_in_process(self):
        executor = SandboxExecutor()
        assert isinstance(executor._backend, InProcessBackend)

    def test_accepts_custom_backend(self):
        class CustomBackend(SandboxBackend):
            @property
            def execution_mode(self) -> str:
                return "custom_test"

            def execute_step(self, step, handler, context):
                return handler(step, context)

        executor = SandboxExecutor(backend=CustomBackend())
        assert executor._backend.execution_mode == "custom_test"

    def test_execution_mode_propagated_to_result(self):
        executor = SandboxExecutor()
        plan = _make_plan(steps=[])
        result = executor.execute_plan(plan)
        assert result.execution_mode == "in_process"

    def test_custom_backend_mode_in_result(self):
        class TestBackend(SandboxBackend):
            @property
            def execution_mode(self) -> str:
                return "test_isolated"

            def execute_step(self, step, handler, context):
                return handler(step, context)

        executor = SandboxExecutor(backend=TestBackend())
        plan = _make_plan(steps=[])
        result = executor.execute_plan(plan)
        assert result.execution_mode == "test_isolated"


# ---------------------------------------------------------------------------
# SandboxResult — execution_mode field
# ---------------------------------------------------------------------------

class TestSandboxResultExecutionMode:
    def test_execution_mode_in_result(self):
        result = SandboxResult(
            execution_id="e1",
            plan_category="test",
            status=SandboxStatus.SUCCESS,
            success=True,
            steps_executed=(),
            steps_succeeded=0,
            steps_failed=0,
            message="done",
            execution_mode="in_process",
        )
        assert result.execution_mode == "in_process"

    def test_execution_mode_in_to_dict(self):
        result = SandboxResult(
            execution_id="e1",
            plan_category="test",
            status=SandboxStatus.SUCCESS,
            success=True,
            steps_executed=(),
            steps_succeeded=0,
            steps_failed=0,
            message="done",
            execution_mode="in_process",
        )
        d = result.to_dict()
        assert "execution_mode" in d
        assert d["execution_mode"] == "in_process"


# ---------------------------------------------------------------------------
# Backward compatibility — existing SandboxExecutor behavior preserved
# ---------------------------------------------------------------------------

class TestSandboxBackwardCompatibility:
    def test_no_handler_gives_skipped(self):
        executor = SandboxExecutor()
        step = _make_step(action_type="UNKNOWN_OP")
        plan = _make_plan(steps=[step])
        result = executor.execute_plan(plan)
        assert result.steps_executed[0].status == SandboxStatus.SKIPPED

    def test_handler_success_gives_success_status(self):
        executor = SandboxExecutor()
        executor.register_handler(
            "RERUN_NODE",
            lambda s, c: {"success": True, "message": "rerun ok"},
        )
        step = _make_step(action_type="RERUN_NODE")
        plan = _make_plan(steps=[step])
        result = executor.execute_plan(plan)
        assert result.success is True
        assert result.steps_executed[0].status == SandboxStatus.SUCCESS

    def test_handler_failure_halts_execution(self):
        executor = SandboxExecutor()
        executor.register_handler(
            "RERUN_NODE",
            lambda s, c: {"success": False, "message": "failed"},
        )
        step1 = _make_step(action_type="RERUN_NODE", step_index=0)
        step2 = _make_step(action_type="RERUN_NODE", step_index=1)
        plan = _make_plan(steps=[step1, step2])
        result = executor.execute_plan(plan)
        assert result.success is False
        # Only first step executed
        assert len(result.steps_executed) == 1

    def test_handler_exception_gives_failed_status(self):
        executor = SandboxExecutor()

        def bad_handler(s, c):
            raise RuntimeError("handler blew up")

        executor.register_handler("RERUN_NODE", bad_handler)
        step = _make_step(action_type="RERUN_NODE")
        plan = _make_plan(steps=[step])
        result = executor.execute_plan(plan)
        assert result.success is False
        assert "blew up" in result.steps_executed[0].message

    def test_empty_plan_succeeds(self):
        executor = SandboxExecutor()
        plan = _make_plan(steps=[])
        result = executor.execute_plan(plan)
        assert result.success is True
        assert result.steps_executed == ()

    def test_result_is_structured_and_immutable(self):
        from dataclasses import FrozenInstanceError
        executor = SandboxExecutor()
        plan = _make_plan(steps=[])
        result = executor.execute_plan(plan)
        assert isinstance(result, SandboxResult)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            result.success = False  # type: ignore[misc]

    def test_timeout_behavior_deterministic(self):
        """
        InProcessBackend has no timeout mechanism — this test verifies
        that the result is always returned (no hang) for simple handlers.
        Subprocess-level timeout is future work.
        """
        import time
        executor = SandboxExecutor()
        executor.register_handler(
            "RERUN_NODE",
            lambda s, c: {"success": True, "message": "fast"},
        )
        step = _make_step(action_type="RERUN_NODE")
        plan = _make_plan(steps=[step])
        start = time.monotonic()
        result = executor.execute_plan(plan)
        elapsed = time.monotonic() - start
        assert result.success is True
        assert elapsed < 1.0  # must complete quickly for in-process

    def test_result_to_dict_is_json_serializable(self):
        import json
        executor = SandboxExecutor()
        plan = _make_plan(steps=[])
        result = executor.execute_plan(plan)
        assert json.dumps(result.to_dict())
