"""
Shared fixtures for the Mode A latency performance test suite (PLAN-N-001/TASK-004).

Provides:
  synthetic_event_factory  — builds GeoEvent-like dicts for multiple sources.
  FakePipelineExecutor     — runs all 12 steps with injected sleep values;
                             uses real StepLatencyGuard and wall-clock timer.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from src.event_pipeline.latency import STEP_BUDGETS

# Ordered step names (mirrors PipelineExecutor.PIPELINE_STEP_ORDER)
_ORDERED_STEPS: list[str] = [
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
# Synthetic event factory
# ---------------------------------------------------------------------------


def synthetic_event_factory(
    intensity: int = 4,
    source: str = "gdelt",
    event_id: str | None = None,
) -> dict[str, Any]:
    """Build a GeoEvent-like dict for pipeline testing.

    Args:
        intensity: Alert intensity level (1–5).
        source:    Data source identifier.  Supported values:
                   ``gdelt``, ``twitter_tier1``, ``edgar``, ``price_anomaly``.
        event_id:  Optional unique identifier; auto-generated if not provided.

    Returns:
        A dict representing a raw geo-event.
    """
    import uuid

    base: dict[str, Any] = {
        "id": event_id or str(uuid.uuid4()),
        "intensity": intensity,
        "source": source,
        "headline": f"Synthetic {source} event (intensity={intensity})",
        "tickers": ["AAPL", "MSFT"],
        "region": "US",
        "category": "geopolitical",
    }

    source_overrides: dict[str, dict[str, Any]] = {
        "twitter_tier1": {
            "tier": "TIER1",
            "category": "social_signal",
        },
        "edgar": {
            "filing_type": "8-K",
            "category": "sec_filing",
        },
        "price_anomaly": {
            "category": "price_anomaly",
            "score_change_pct": 4.5,
        },
    }
    base.update(source_overrides.get(source, {}))
    return base


# ---------------------------------------------------------------------------
# FakePipelineExecutor
# ---------------------------------------------------------------------------


class FakePipelineExecutor:
    """Pipeline executor that runs all 12 steps with configurable artificial delays.

    Uses the real ``StepLatencyGuard`` so that budget breaches raise
    ``StepTimeoutError`` exactly as the production executor would.
    Wall-clock timing uses ``time.perf_counter_ns()`` to match PipelineExecutor.

    Args:
        step_delays_ms: Mapping of step_name → sleep duration in ms.
                        Steps not in the mapping sleep for 0 ms.

    Usage::

        executor = FakePipelineExecutor(step_delays_ms={"classify_event": 2_500})
        latency_ms = await executor.run(event)
    """

    def __init__(self, step_delays_ms: dict[str, int] | None = None) -> None:
        self._step_delays: dict[str, int] = step_delays_ms or {}

    async def _run_step(self, step_name: str) -> str:
        """Run a single step with real StepLatencyGuard and injected delay."""
        from src.event_pipeline.latency import StepLatencyGuard

        budget = STEP_BUDGETS[step_name]
        delay_ms = self._step_delays.get(step_name, 0)
        async with StepLatencyGuard(budget):
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
        return f"{step_name}:ok"

    async def run(self, event: dict[str, Any]) -> float:
        """Execute all 12 steps and return the total wall-clock latency in ms.

        Args:
            event: Raw geo-event dict (not inspected — delays are pre-configured).

        Returns:
            Total pipeline wall-clock time in milliseconds.

        Raises:
            StepTimeoutError: If any step exceeds its budget.
        """
        start_ns = time.perf_counter_ns()
        for step_name in _ORDERED_STEPS:
            await self._run_step(step_name)
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        return elapsed_ms


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gdelt_event():
    """A single synthetic GDELT event at intensity 4."""
    return synthetic_event_factory(intensity=4, source="gdelt")


@pytest.fixture()
def twitter_tier1_event():
    """A single synthetic TIER1 tweet event."""
    return synthetic_event_factory(intensity=5, source="twitter_tier1")


@pytest.fixture()
def edgar_event():
    """A single synthetic SEC filing event."""
    return synthetic_event_factory(intensity=3, source="edgar")


@pytest.fixture()
def price_anomaly_event():
    """A single synthetic price-anomaly (score-change) event."""
    return synthetic_event_factory(intensity=3, source="price_anomaly")
