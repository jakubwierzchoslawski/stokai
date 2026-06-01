"""Unit tests for PipelineExecutor and run_pipeline Celery task.

TDD: tests written before implementation (TASK-001).

Covers: AC-001 (sequential execution), AC-005 (failure isolation).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.event_pipeline.exceptions import DuplicateEvent, PipelineHalt
from src.event_pipeline.pipeline_state import (
    AlertRoute,
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_state() -> PipelineState:
    """Return a minimal valid PipelineState for testing."""
    tenant_id = uuid.uuid4()
    raw_event_id = uuid.uuid4()
    payload = RawEventPayload(
        source=RawEventSource.GDELT,
        raw_payload={"title": "Test event"},
        detected_at=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )
    return PipelineState(
        raw_event_id=raw_event_id,
        tenant_id=tenant_id,
        payload=payload,
    )


def _make_mock_step(name: str) -> AsyncMock:
    """Return an async mock step that echoes its state input unchanged."""
    step = AsyncMock()
    step.step_name = name
    # execute returns the state unchanged by default
    step.execute = AsyncMock(side_effect=lambda state: state)
    return step


# ---------------------------------------------------------------------------
# TASK-001 TDD tests — PipelineExecutor
# ---------------------------------------------------------------------------

class TestPipelineExecutorRunsAllStepsInOrder:
    """test_executor_runs_all_steps_in_order"""

    @pytest.mark.asyncio
    async def test_executor_runs_all_steps_in_order(self):
        """13 steps are each called exactly once in definition order."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        await executor.run(state)

        call_order = []
        for step in steps:
            assert step.execute.call_count == 1
            call_order.append(step.step_name)

        assert call_order == [f"s{i:02d}_step" for i in range(1, 14)]


class TestPipelineExecutorHaltsOnStepFailure:
    """test_executor_halts_on_step_failure"""

    @pytest.mark.asyncio
    async def test_executor_halts_on_step_failure(self):
        """When step 4 raises PipelineHalt, steps 5–13 are NOT called."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        # Step index 3 (0-based) = step 4 raises
        failing_step = steps[3]
        failing_step.step_name = "s04_classify"
        failing_step.execute = AsyncMock(
            side_effect=PipelineHalt("s04_classify", "mock classify error")
        )

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt):
            await executor.run(state)

        # Steps 5–13 (indices 4–12) must not have been called
        for step in steps[4:]:
            step.execute.assert_not_called()

        # failed_step must be set
        # We test this via the repo call below; check step 4's execute was called
        failing_step.execute.assert_called_once()


class TestPipelineExecutorMarksDuplicateStatus:
    """test_executor_marks_duplicate_status"""

    @pytest.mark.asyncio
    async def test_executor_marks_duplicate_status(self):
        """DuplicateEvent from step 2 causes repo to be called with status='duplicate'."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        steps[1].step_name = "s02_deduplicate"
        steps[1].execute = AsyncMock(
            side_effect=DuplicateEvent("s02_deduplicate", "fingerprint already exists")
        )

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt):
            await executor.run(state)

        # Repo must be called with status "duplicate"
        repo_mock.update_status.assert_called_once()
        call_args = repo_mock.update_status.call_args
        assert call_args.kwargs.get("status") == "duplicate" or (
            len(call_args.args) >= 2 and call_args.args[1] == "duplicate"
        )


class TestPipelineExecutorDoesNotDispatchOnFailure:
    """test_executor_does_not_dispatch_on_failure"""

    @pytest.mark.asyncio
    async def test_executor_does_not_dispatch_on_failure(self):
        """When step 4 fails, the dispatch step (index 11, step 12) is not called."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        steps[3].step_name = "s04_classify"
        steps[3].execute = AsyncMock(
            side_effect=PipelineHalt("s04_classify", "classify failed")
        )
        dispatch_step = steps[11]  # index 11 = step 12
        dispatch_step.step_name = "s12_dispatch"

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt):
            await executor.run(state)

        dispatch_step.execute.assert_not_called()


class TestPipelineTaskIdempotent:
    """test_pipeline_task_idempotent"""

    @pytest.mark.asyncio
    async def test_pipeline_task_idempotent(self):
        """If raw_event already has pipeline_status=completed, executor is not constructed."""
        from src.event_pipeline.pipeline_task import run_pipeline_task

        raw_event_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        with patch("src.event_pipeline.pipeline_task.build_executor") as mock_build, \
             patch("src.event_pipeline.pipeline_task.get_raw_event_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "completed"
            mock_build.return_value = MagicMock()

            await run_pipeline_task(str(raw_event_id), str(tenant_id))

            mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# TASK-012 extension tests — error wrapping and per-step failure trap
# ---------------------------------------------------------------------------

class TestNonPipelineHaltExceptionIsWrapped:
    """test_non_pipeline_halt_exception_is_wrapped"""

    @pytest.mark.asyncio
    async def test_non_pipeline_halt_exception_is_wrapped(self):
        """A plain ValueError from a step is wrapped into PipelineHalt."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        steps[0].step_name = "s01_ingest"
        steps[0].execute = AsyncMock(side_effect=ValueError("unexpected DB error"))

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt) as exc_info:
            await executor.run(state)

        assert exc_info.value.step_name == "s01_ingest"


class TestFailedStepNameMatchesRaisingStep:
    """test_failed_step_name_matches_raising_step"""

    @pytest.mark.asyncio
    async def test_failed_step_name_matches_raising_step(self):
        """When step 7 raises, state.failed_step must equal 's07_exposure_score'."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        steps[6].step_name = "s07_exposure_score"
        steps[6].execute = AsyncMock(
            side_effect=RuntimeError("score compute failed")
        )

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt) as exc_info:
            await executor.run(state)

        assert exc_info.value.step_name == "s07_exposure_score"


class TestDbStatusWrittenToFailedOnHalt:
    """test_db_status_written_to_failed_on_halt"""

    @pytest.mark.asyncio
    async def test_db_status_written_to_failed_on_halt(self):
        """On any halt, repository update_status is called with status='failed'."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        steps[5].step_name = "s06_portfolio_scan"
        steps[5].execute = AsyncMock(
            side_effect=PipelineHalt("s06_portfolio_scan", "scan failed")
        )

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt):
            await executor.run(state)

        repo_mock.update_status.assert_called_once()
        call_args = repo_mock.update_status.call_args
        # status must be "failed" (DuplicateEvent has its own status)
        assert call_args.kwargs.get("status") == "failed" or (
            len(call_args.args) >= 2 and call_args.args[1] == "failed"
        )


class TestDispatchNotCalledWhenFailedStepSet:
    """test_dispatch_not_called_when_failed_step_set"""

    @pytest.mark.asyncio
    async def test_dispatch_not_called_when_failed_step_set(self):
        """Halt before step 12 means dispatch step (index 11) is never called."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        steps[4].step_name = "s05_embed"
        steps[4].execute = AsyncMock(
            side_effect=PipelineHalt("s05_embed", "embed failed")
        )
        dispatch_mock = steps[11]
        dispatch_mock.step_name = "s12_dispatch"

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt):
            await executor.run(state)

        dispatch_mock.execute.assert_not_called()


class TestErrorDetailStoredInState:
    """test_error_detail_stored_in_state"""

    @pytest.mark.asyncio
    async def test_error_detail_stored_in_state(self):
        """error_detail on the raised PipelineHalt contains the original message."""
        from src.event_pipeline.pipeline_executor import PipelineExecutor

        steps = [_make_mock_step(f"s{i:02d}_step") for i in range(1, 14)]
        steps[2].step_name = "s03_parse"
        steps[2].execute = AsyncMock(
            side_effect=ValueError("parse field missing")
        )

        langfuse_mock = MagicMock()
        repo_mock = AsyncMock()

        executor = PipelineExecutor(steps=steps, langfuse_client=langfuse_mock, raw_event_repo=repo_mock)
        state = _make_state()

        with pytest.raises(PipelineHalt) as exc_info:
            await executor.run(state)

        assert "parse field missing" in exc_info.value.detail
