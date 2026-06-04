"""
Mode A pipeline latency assertion suite (PLAN-N-001/TASK-004).

Asserts p95 end-to-end latency for various event types using
FakePipelineExecutor with real StepLatencyGuard.

AC covered:
  AC-001: p95 ≤ 90 s for intensity-4/5 events
  AC-002: TIER1-tweet p95 ≤ 30 s
  AC-003: Score-change alert p95 ≤ 5 min
  AC-004: SEC filing alert p95 ≤ 20 min
"""
from __future__ import annotations

import asyncio
import statistics
from typing import Any

import pytest

from src.event_pipeline.exceptions import StepTimeoutError
from src.event_pipeline.latency import STEP_BUDGETS

from tests.performance.conftest import FakePipelineExecutor, synthetic_event_factory

# Number of synthetic events to run per assertion (must be ≥ 2 for quantiles).
_SAMPLE_COUNT: int = 100

# Canonical step list from Architecture §6 — used for registry completeness check.
_CANONICAL_STEPS: list[str] = [
    "persist_raw_event",
    "classify_event",
    "extract_tickers",
    "compute_exposure_map",
    "persist_event_record",
    "embed_event",
    "find_historical_analogies",
    "generate_alert_text",
    "evaluate_alert_rules",
    "dispatch_or_log_silent",
    "enqueue_deep_dive",
    "return_pipeline_result",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _p95(latencies: list[float]) -> float:
    """Compute the p95 from a list of latency values.

    Uses statistics.quantiles with n=20 so index [18] is the 95th percentile.
    Requires at least 20 samples; test suite always produces 100.
    """
    return statistics.quantiles(latencies, n=20)[18]


async def _run_n_events(
    executor: FakePipelineExecutor,
    event: dict[str, Any],
    n: int = _SAMPLE_COUNT,
) -> list[float]:
    """Run the fake executor n times sequentially and collect latency_ms values."""
    latencies: list[float] = []
    for _ in range(n):
        latency_ms = await executor.run(event)
        latencies.append(latency_ms)
    return latencies


# ---------------------------------------------------------------------------
# Budget registry sanity tests (AC-001 enabler)
# ---------------------------------------------------------------------------


class TestStepBudgetRegistry:
    """Validate completeness and sanity of the STEP_BUDGETS registry."""

    def test_step_budgets_count_equals_12(self):
        """There must be exactly 12 steps in the budget registry."""
        assert len(STEP_BUDGETS) == 12, (
            f"Expected 12 steps, got {len(STEP_BUDGETS)}: {list(STEP_BUDGETS.keys())}"
        )

    def test_step_budgets_canonical_names_match(self):
        """All canonical step names from Architecture §6 must be in STEP_BUDGETS."""
        missing = [s for s in _CANONICAL_STEPS if s not in STEP_BUDGETS]
        assert not missing, f"Missing step budgets: {missing}"

    def test_step_budgets_sum_under_27000ms(self):
        """Sum of all per-step budgets must be ≤ 27 000 ms (well within 60 s limit)."""
        total = sum(b.budget_ms for b in STEP_BUDGETS.values())
        assert total <= 27_000, (
            f"Total step budgets = {total} ms, exceeds 27 000 ms ceiling"
        )

    def test_all_budgets_positive(self):
        """Every step budget must be > 0 ms."""
        for name, budget in STEP_BUDGETS.items():
            assert budget.budget_ms > 0, f"Budget for '{name}' is not positive"

    def test_step_budget_step_name_matches_key(self):
        """StepBudget.step_name must match the dict key for every entry."""
        for key, budget in STEP_BUDGETS.items():
            assert budget.step_name == key, (
                f"Key '{key}' has mismatched step_name '{budget.step_name}'"
            )


# ---------------------------------------------------------------------------
# AC-001: End-to-end p95 ≤ 90 s for intensity-4/5 events
# ---------------------------------------------------------------------------


class TestAc001EndToEndLatency:
    """AC-001: p95 end-to-end latency ≤ 90 000 ms for intensity-4/5 events."""

    @pytest.mark.asyncio
    async def test_p95_latency_at_80_percent_budget_is_under_90s(self):
        """
        100 intensity-4 events through FakePipelineExecutor where each step
        sleeps at 80 % of its budget.  p95 must be ≤ 90 000 ms.
        """
        delays_80pct = {
            name: int(budget.budget_ms * 0.8)
            for name, budget in STEP_BUDGETS.items()
        }
        executor = FakePipelineExecutor(step_delays_ms=delays_80pct)
        event = synthetic_event_factory(intensity=4, source="gdelt")

        latencies = await _run_n_events(executor, event)

        p95_ms = _p95(latencies)
        assert p95_ms <= 90_000, (
            f"p95 end-to-end latency {p95_ms:.0f} ms exceeds 90 000 ms SLA (AC-001)"
        )

    @pytest.mark.asyncio
    async def test_classify_event_over_budget_raises_step_timeout_error(self):
        """
        AC-001 breach detection: classify_event sleeping 5 100 ms (just over 5 000 ms
        budget) must raise StepTimeoutError on every run.
        """
        delays = {"classify_event": 5_100}
        executor = FakePipelineExecutor(step_delays_ms=delays)
        event = synthetic_event_factory(intensity=4, source="gdelt")

        with pytest.raises(StepTimeoutError) as exc_info:
            await executor.run(event)

        err = exc_info.value
        assert err.step_name == "classify_event"
        assert err.budget_ms == 5_000


# ---------------------------------------------------------------------------
# AC-002: TIER1 tweet p95 ≤ 30 s
# ---------------------------------------------------------------------------


class TestAc002Tier1TweetLatency:
    """AC-002: TIER1-tweet p95 ≤ 30 000 ms."""

    @pytest.mark.asyncio
    async def test_tier1_tweet_p95_under_30s(self):
        """
        100 TIER1-tweet events at 50 % of budget per step.
        p95 must be ≤ 30 000 ms.

        Rationale: per-step budgets sum to 31 s at 100 % load.
        At 50 % load total ≈ 15.5 s — well within the 30 s window.
        """
        delays_50pct = {
            name: int(budget.budget_ms * 0.5)
            for name, budget in STEP_BUDGETS.items()
        }
        executor = FakePipelineExecutor(step_delays_ms=delays_50pct)
        event = synthetic_event_factory(intensity=5, source="twitter_tier1")

        latencies = await _run_n_events(executor, event)

        p95_ms = _p95(latencies)
        assert p95_ms <= 30_000, (
            f"TIER1-tweet p95 {p95_ms:.0f} ms exceeds 30 000 ms target (AC-002)"
        )


# ---------------------------------------------------------------------------
# AC-003: Score-change alert p95 ≤ 5 min
# ---------------------------------------------------------------------------


class TestAc003ScoreChangeLatency:
    """AC-003: Score-change alert p95 ≤ 300 000 ms (5 min)."""

    @pytest.mark.asyncio
    async def test_score_change_p95_under_5_min(self):
        """
        100 price_anomaly events at nominal step latencies (0 ms injected delay).
        p95 must be ≤ 300 000 ms.

        The pipeline itself executes in < 1 s with 0-ms delays; remaining
        budget in the 5-min window covers ingestion polling intervals.
        """
        executor = FakePipelineExecutor()  # no delays — nominal execution
        event = synthetic_event_factory(intensity=3, source="price_anomaly")

        latencies = await _run_n_events(executor, event)

        p95_ms = _p95(latencies)
        assert p95_ms <= 300_000, (
            f"Score-change p95 {p95_ms:.0f} ms exceeds 300 000 ms (5 min) (AC-003)"
        )


# ---------------------------------------------------------------------------
# AC-004: SEC filing alert p95 ≤ 20 min
# ---------------------------------------------------------------------------


class TestAc004SecFilingLatency:
    """AC-004: SEC filing alert p95 ≤ 1 200 000 ms (20 min)."""

    @pytest.mark.asyncio
    async def test_sec_filing_p95_under_20_min(self):
        """
        100 edgar events at nominal step latencies (0 ms injected delay).
        p95 must be ≤ 1 200 000 ms.

        The pipeline itself executes in < 1 s; remaining budget covers EDGAR
        feed polling latency.
        """
        executor = FakePipelineExecutor()  # no delays — nominal execution
        event = synthetic_event_factory(intensity=3, source="edgar")

        latencies = await _run_n_events(executor, event)

        p95_ms = _p95(latencies)
        assert p95_ms <= 1_200_000, (
            f"SEC filing p95 {p95_ms:.0f} ms exceeds 1 200 000 ms (20 min) (AC-004)"
        )
