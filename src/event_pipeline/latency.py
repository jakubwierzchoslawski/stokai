"""
Latency budget registry and step timeout guard for the Mode A Reactive Pipeline.

Architecture §6 defines per-step latency budgets.  All 12 steps are registered
in STEP_BUDGETS.  StepLatencyGuard is an async context manager that enforces the
budget and raises StepTimeoutError on breach.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from types import TracebackType
from typing import Optional, Type

from src.event_pipeline.exceptions import StepTimeoutError


@dataclass(frozen=True)
class StepBudget:
    """Immutable latency budget for one pipeline step.

    Attributes:
        step_name: Canonical step name (matches PipelineExecutor step names).
        budget_ms: Maximum allowed elapsed time in milliseconds.
        is_llm:    True when the step calls an external LLM/embedding API.
    """

    step_name: str
    budget_ms: int
    is_llm: bool


# ---------------------------------------------------------------------------
# Authoritative step budget registry (Architecture §6)
# Sum of all budgets: 31 000 ms — well within the 60 000 ms processing limit.
# ---------------------------------------------------------------------------
STEP_BUDGETS: dict[str, StepBudget] = {
    "persist_raw_event": StepBudget(
        step_name="persist_raw_event", budget_ms=1_000, is_llm=False
    ),
    "classify_event": StepBudget(
        step_name="classify_event", budget_ms=5_000, is_llm=True
    ),
    "extract_tickers": StepBudget(
        step_name="extract_tickers", budget_ms=3_000, is_llm=True
    ),
    "compute_exposure_map": StepBudget(
        step_name="compute_exposure_map", budget_ms=3_000, is_llm=False
    ),
    "persist_event_record": StepBudget(
        step_name="persist_event_record", budget_ms=1_000, is_llm=False
    ),
    "embed_event": StepBudget(
        step_name="embed_event", budget_ms=2_000, is_llm=True
    ),
    "find_historical_analogies": StepBudget(
        step_name="find_historical_analogies", budget_ms=3_000, is_llm=False
    ),
    "generate_alert_text": StepBudget(
        step_name="generate_alert_text", budget_ms=8_000, is_llm=True
    ),
    "evaluate_alert_rules": StepBudget(
        step_name="evaluate_alert_rules", budget_ms=1_000, is_llm=False
    ),
    "dispatch_or_log_silent": StepBudget(
        step_name="dispatch_or_log_silent", budget_ms=2_000, is_llm=False
    ),
    "enqueue_deep_dive": StepBudget(
        step_name="enqueue_deep_dive", budget_ms=1_000, is_llm=False
    ),
    "return_pipeline_result": StepBudget(
        step_name="return_pipeline_result", budget_ms=1_000, is_llm=False
    ),
}

_CANONICAL_STEP_NAMES: list[str] = list(STEP_BUDGETS.keys())


class StepLatencyGuard:
    """Async context manager that enforces a per-step latency budget.

    Usage::

        budget = STEP_BUDGETS["classify_event"]
        async with StepLatencyGuard(budget) as guard:
            result = await classify_event_coroutine(...)
        elapsed = guard.actual_ms   # available after __aexit__

    Raises:
        StepTimeoutError: If the step body completes but the elapsed wall-clock
                          time exceeds ``budget.budget_ms``.  The error carries
                          ``step_name``, ``budget_ms``, and ``actual_ms``.

    Note: This guard uses a wall-clock check on ``__aexit__`` rather than
    ``asyncio.wait_for`` so that it does not forcefully cancel the coroutine
    (which can leave HTTP connections in an indeterminate state with some LLM
    clients).  To add hard cancellation, wrap the coroutine with
    ``asyncio.wait_for`` *before* entering this context manager.
    """

    def __init__(self, budget: StepBudget) -> None:
        self._budget = budget
        self._start_ns: int = 0
        self._actual_ms: Optional[float] = None

    async def __aenter__(self) -> "StepLatencyGuard":
        self._start_ns = time.perf_counter_ns()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        elapsed_ns = time.perf_counter_ns() - self._start_ns
        self._actual_ms = elapsed_ns / 1_000_000.0

        # If the step already failed for another reason, do not mask that error.
        if exc_type is not None:
            return False  # propagate original exception

        # Check budget breach only when step completed without error.
        if self._actual_ms > self._budget.budget_ms:
            raise StepTimeoutError(
                step_name=self._budget.step_name,
                budget_ms=self._budget.budget_ms,
                actual_ms=self._actual_ms,
            )

        return False  # do not suppress exceptions

    @property
    def actual_ms(self) -> float:
        """Elapsed wall-clock time in milliseconds.  Available after ``__aexit__``."""
        if self._actual_ms is None:
            raise RuntimeError(
                "actual_ms is not available until the context manager has exited."
            )
        return self._actual_ms
