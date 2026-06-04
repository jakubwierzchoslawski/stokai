"""
Unit tests for WorkflowSoftTimeoutGuard — PLAN-N-002 TASK-004.

TDD: tests written before finalising the implementation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType
from src.ai.workflows.timeout_guard import WorkflowSoftTimeoutGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**kwargs) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid4(),
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=uuid4(),
        user_id=uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        **kwargs,
    )


def _make_mock_repository(raise_on_save: Exception | None = None) -> AsyncMock:
    repo = AsyncMock()
    if raise_on_save:
        repo.save_timeout = AsyncMock(side_effect=raise_on_save)
    else:
        repo.save_timeout = AsyncMock(return_value=None)
    return repo


def _make_slte():
    """Return the real SoftTimeLimitExceeded class or a stand-in."""
    try:
        from celery.exceptions import SoftTimeLimitExceeded
        return SoftTimeLimitExceeded
    except ImportError:
        class SoftTimeLimitExceeded(Exception):
            pass
        return SoftTimeLimitExceeded


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWorkflowSoftTimeoutGuardSuppression:
    @pytest.mark.asyncio
    async def test_guard_suppresses_soft_time_limit_exceeded(self):
        """SoftTimeLimitExceeded inside the block must NOT propagate."""
        SLTE = _make_slte()
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo)
        # Should not raise
        async with guard:
            raise SLTE("time limit")

    @pytest.mark.asyncio
    async def test_guard_does_not_suppress_other_exceptions(self):
        """ValueError inside the block must propagate; save_timeout must NOT be called."""
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo)
        with pytest.raises(ValueError):
            async with guard:
                raise ValueError("unrelated error")

        repo.save_timeout.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_noop_on_clean_exit(self):
        """Clean exit from block: save_timeout NOT called, state unchanged."""
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo)
        async with guard:
            pass  # no exception

        repo.save_timeout.assert_not_called()
        assert state.status == WorkflowStatus.RUNNING
        assert state.partial_result is False


class TestWorkflowSoftTimeoutGuardStateTransitions:
    @pytest.mark.asyncio
    async def test_guard_sets_state_status_to_timeout(self):
        """After SoftTimeLimitExceeded, final_state.status must be TIMEOUT."""
        SLTE = _make_slte()
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo)
        async with guard:
            raise SLTE()

        assert guard._final_state.status == WorkflowStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_guard_sets_partial_result_true(self):
        SLTE = _make_slte()
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo)
        async with guard:
            raise SLTE()

        assert guard._final_state.partial_result is True

    @pytest.mark.asyncio
    async def test_guard_sets_timeout_at(self):
        SLTE = _make_slte()
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo)
        async with guard:
            raise SLTE()

        assert guard._final_state.timeout_at is not None
        assert isinstance(guard._final_state.timeout_at, datetime)


class TestWorkflowSoftTimeoutGuardRepository:
    @pytest.mark.asyncio
    async def test_guard_calls_save_timeout_on_repository(self):
        """save_timeout must be called with the correct workflow_id."""
        SLTE = _make_slte()
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo)
        async with guard:
            raise SLTE()

        repo.save_timeout.assert_called_once()
        call_kwargs = repo.save_timeout.call_args
        assert call_kwargs.kwargs["workflow_id"] == state.workflow_id
        assert call_kwargs.kwargs["timeout_at"] is not None

    @pytest.mark.asyncio
    async def test_guard_does_not_raise_if_repository_fails(self):
        """Repository save failure must not propagate from the guard."""
        SLTE = _make_slte()
        state = _make_state()
        repo = _make_mock_repository(raise_on_save=RuntimeError("DB down"))

        guard = WorkflowSoftTimeoutGuard(state, repo)
        # Should not raise
        async with guard:
            raise SLTE()


class TestWorkflowSoftTimeoutGuardLangfuse:
    @pytest.mark.asyncio
    async def test_guard_writes_langfuse_score_workflow_timeout_equals_1(self):
        """On timeout, score 'workflow_timeout' = 1 must be written."""
        SLTE = _make_slte()
        state = _make_state(langfuse_trace_id="trace-abc-123")
        repo = _make_mock_repository()
        langfuse_client = MagicMock()

        guard = WorkflowSoftTimeoutGuard(state, repo, langfuse_client=langfuse_client)
        async with guard:
            raise SLTE()

        # score() should have been called with workflow_timeout = 1
        score_calls = langfuse_client.score.call_args_list
        timeout_score_calls = [
            c for c in score_calls
            if c.kwargs.get("name") == "workflow_timeout"
        ]
        assert len(timeout_score_calls) == 1
        assert timeout_score_calls[0].kwargs["value"] == 1

    @pytest.mark.asyncio
    async def test_guard_writes_duration_ms_to_langfuse(self):
        """On timeout, duration_ms score must be written to the trace."""
        SLTE = _make_slte()
        state = _make_state(langfuse_trace_id="trace-dur-456")
        repo = _make_mock_repository()
        langfuse_client = MagicMock()

        guard = WorkflowSoftTimeoutGuard(state, repo, langfuse_client=langfuse_client)
        async with guard:
            raise SLTE()

        score_calls = langfuse_client.score.call_args_list
        duration_calls = [
            c for c in score_calls
            if "duration_ms" in c.kwargs.get("name", "")
        ]
        assert len(duration_calls) == 1

    @pytest.mark.asyncio
    async def test_guard_does_not_raise_if_langfuse_unavailable(self):
        """langfuse_client=None must not cause any exception."""
        SLTE = _make_slte()
        state = _make_state()
        repo = _make_mock_repository()

        guard = WorkflowSoftTimeoutGuard(state, repo, langfuse_client=None)
        # Should not raise
        async with guard:
            raise SLTE()

    @pytest.mark.asyncio
    async def test_guard_does_not_raise_if_langfuse_score_fails(self):
        """Langfuse.score() raising must not propagate out of the guard."""
        SLTE = _make_slte()
        state = _make_state(langfuse_trace_id="trace-fail")
        repo = _make_mock_repository()
        langfuse_client = MagicMock()
        langfuse_client.score.side_effect = ConnectionError("Langfuse unreachable")

        guard = WorkflowSoftTimeoutGuard(state, repo, langfuse_client=langfuse_client)
        # Should not raise
        async with guard:
            raise SLTE()

    @pytest.mark.asyncio
    async def test_guard_skips_langfuse_score_when_no_trace_id(self):
        """If state.langfuse_trace_id is None, no Langfuse score should be written."""
        SLTE = _make_slte()
        state = _make_state()  # langfuse_trace_id=None by default
        repo = _make_mock_repository()
        langfuse_client = MagicMock()

        guard = WorkflowSoftTimeoutGuard(state, repo, langfuse_client=langfuse_client)
        async with guard:
            raise SLTE()

        # score() should NOT have been called (no trace_id to attach to)
        langfuse_client.score.assert_not_called()
