"""
Unit tests for WorkflowTimeoutGuard (PLAN-F-010 TASK-003).

TDD: written before implementation.
"""
from __future__ import annotations

import asyncio

import pytest

from src.ai.workflows.event_deep_dive.exceptions import WorkflowTimeoutError
from src.ai.workflows.event_deep_dive.timeout_guard import WorkflowTimeoutGuard


class TestWorkflowTimeoutGuard:
    @pytest.mark.asyncio
    async def test_no_timeout_when_within_limit(self):
        """Coroutine completing within the hard_limit_seconds should not raise."""
        async def fast_task():
            return "done"

        async with WorkflowTimeoutGuard(hard_limit_seconds=5):
            result = await fast_task()

        assert result == "done"

    @pytest.mark.asyncio
    async def test_raises_workflow_timeout_error_on_exceed(self):
        """Coroutine exceeding hard_limit_seconds must raise WorkflowTimeoutError."""
        async def slow_task():
            await asyncio.sleep(10)

        with pytest.raises(WorkflowTimeoutError) as exc_info:
            async with WorkflowTimeoutGuard(hard_limit_seconds=0.01):
                await slow_task()

        err = exc_info.value
        assert err.elapsed_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_error_has_to_dict(self):
        """WorkflowTimeoutError.to_dict() returns a JSON-serializable dict."""
        async def slow_task():
            await asyncio.sleep(10)

        with pytest.raises(WorkflowTimeoutError) as exc_info:
            async with WorkflowTimeoutGuard(hard_limit_seconds=0.01):
                await slow_task()

        d = exc_info.value.to_dict()
        assert "error" in d
        assert "elapsed_seconds" in d

    @pytest.mark.asyncio
    async def test_elapsed_seconds_in_error_is_non_negative(self):
        """elapsed_seconds in WorkflowTimeoutError must be >= 0."""
        async def slow_task():
            await asyncio.sleep(10)

        with pytest.raises(WorkflowTimeoutError) as exc_info:
            async with WorkflowTimeoutGuard(hard_limit_seconds=0.01):
                await slow_task()

        assert exc_info.value.elapsed_seconds >= 0.0
