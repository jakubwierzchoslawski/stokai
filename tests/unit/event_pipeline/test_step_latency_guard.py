"""
Unit tests for StepLatencyGuard and PipelineExecutor integration.

TDD test suite for TASK-002 (PLAN-N-001).
Tests are written before implementation — they define the expected behaviour.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_pipeline.exceptions import StepTimeoutError
from src.event_pipeline.latency import STEP_BUDGETS, StepBudget, StepLatencyGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_budget(step_name: str = "test_step", budget_ms: int = 50) -> StepBudget:
    return StepBudget(step_name=step_name, budget_ms=budget_ms, is_llm=False)


async def fast_step() -> str:
    """Coroutine that completes quickly (≈ 10 ms)."""
    await asyncio.sleep(0.01)
    return "done"


async def slow_step() -> str:
    """Coroutine that always overshoots a 50 ms budget (≈ 200 ms)."""
    await asyncio.sleep(0.2)
    return "done"


# ---------------------------------------------------------------------------
# StepLatencyGuard — unit tests
# ---------------------------------------------------------------------------


class TestStepLatencyGuard:
    """Tests for the async context manager alone."""

    @pytest.mark.asyncio
    async def test_step_under_budget_completes_without_raising(self):
        """A step completing in ~10 ms under a 50 ms budget must not raise."""
        budget = make_budget(budget_ms=50)
        async with StepLatencyGuard(budget) as guard:
            await asyncio.sleep(0.01)
        # If we reached here without StepTimeoutError the test passes.
        assert guard.actual_ms < 50

    @pytest.mark.asyncio
    async def test_step_over_budget_raises_step_timeout_error(self):
        """A step completing in ~200 ms under a 50 ms budget must raise StepTimeoutError."""
        budget = make_budget(step_name="slow_step", budget_ms=50)
        with pytest.raises(StepTimeoutError) as exc_info:
            async with StepLatencyGuard(budget):
                await asyncio.sleep(0.2)

        err = exc_info.value
        assert err.step_name == "slow_step"
        assert err.budget_ms == 50
        assert err.actual_ms > 50  # definitely exceeded

    @pytest.mark.asyncio
    async def test_actual_ms_not_available_before_exit(self):
        """Reading actual_ms before __aexit__ must raise RuntimeError."""
        budget = make_budget()
        guard = StepLatencyGuard(budget)
        # Not used as context manager yet.
        with pytest.raises(RuntimeError):
            _ = guard.actual_ms

    @pytest.mark.asyncio
    async def test_original_exception_propagates_without_masking(self):
        """If the step raises a non-timeout error, that error is not masked."""
        budget = make_budget(budget_ms=50)
        with pytest.raises(ValueError, match="original error"):
            async with StepLatencyGuard(budget):
                raise ValueError("original error")

    @pytest.mark.asyncio
    async def test_actual_ms_available_after_successful_exit(self):
        """actual_ms is readable after the guard exits normally."""
        budget = make_budget(budget_ms=200)
        async with StepLatencyGuard(budget) as guard:
            await asyncio.sleep(0.01)
        assert isinstance(guard.actual_ms, float)
        assert guard.actual_ms >= 0


# ---------------------------------------------------------------------------
# PipelineExecutor integration tests
# ---------------------------------------------------------------------------


def _make_fake_executor(step_delays_ms: dict[str, int]):
    """
    Build a minimal PipelineExecutor-like object that runs all 12 steps
    with injected delays and uses real StepLatencyGuard.

    This is used before the full PipelineExecutor is implemented (TDD approach).
    """
    from src.event_pipeline.latency import STEP_BUDGETS, StepLatencyGuard

    ORDERED_STEPS = list(STEP_BUDGETS.keys())

    class FakeExecutor:
        def __init__(self, delays: dict[str, int]) -> None:
            self._delays = delays  # step_name -> sleep_ms

        async def _run_step(self, step_name: str, delay_ms: int) -> str:
            budget = STEP_BUDGETS[step_name]
            async with StepLatencyGuard(budget):
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)
            return f"{step_name}:ok"

        async def run(self) -> dict[str, Any]:
            results: dict[str, Any] = {}
            for step_name in ORDERED_STEPS:
                delay_ms = self._delays.get(step_name, 0)
                results[step_name] = await self._run_step(step_name, delay_ms)
            return results

    return FakeExecutor(step_delays_ms)


class TestPipelineExecutorLatencyGuardIntegration:
    """Integration tests: StepLatencyGuard wired into an executor-like object."""

    @pytest.mark.asyncio
    async def test_classify_event_over_budget_propagates_step_timeout_error(self):
        """
        classify_event sleeping 6 000 ms (> 5 000 ms budget) must propagate
        StepTimeoutError with step_name='classify_event'.
        """
        delays = {"classify_event": 6_000}
        executor = _make_fake_executor(delays)
        with pytest.raises(StepTimeoutError) as exc_info:
            await executor.run()
        err = exc_info.value
        assert err.step_name == "classify_event"
        assert err.budget_ms == 5_000
        assert err.actual_ms >= 5_000

    @pytest.mark.asyncio
    async def test_all_steps_within_budget_executor_returns_successfully(self):
        """
        All 12 steps with 0 ms delay (well within budget) must return
        a dict with an entry for every step.
        """
        executor = _make_fake_executor({})
        results = await executor.run()
        assert len(results) == 12
        for step_name in STEP_BUDGETS:
            assert step_name in results

    @pytest.mark.asyncio
    async def test_step_timeout_error_carries_correct_step_name(self):
        """
        StepTimeoutError must carry the exact step name that caused the breach,
        not a generic or default name.
        """
        delays = {"embed_event": 3_000}  # embed_event has 2 000 ms budget
        executor = _make_fake_executor(delays)
        with pytest.raises(StepTimeoutError) as exc_info:
            await executor.run()
        assert exc_info.value.step_name == "embed_event"

    @pytest.mark.asyncio
    async def test_step_timeout_error_actual_ms_reflects_real_elapsed_time(self):
        """actual_ms in StepTimeoutError must be >= budget_ms on breach."""
        delays = {"enqueue_deep_dive": 2_000}  # 1 000 ms budget
        executor = _make_fake_executor(delays)
        with pytest.raises(StepTimeoutError) as exc_info:
            await executor.run()
        err = exc_info.value
        assert err.actual_ms >= err.budget_ms
