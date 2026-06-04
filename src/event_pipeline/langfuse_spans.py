"""
Langfuse span context manager for per-step latency observability.

LangfuseSpanContext wraps a Langfuse child span for one pipeline step.
On exit it writes latency_ms, budget_ms, step_name, and sla_breach to the
span's metadata.  If the step raises StepTimeoutError the span is marked
with level='ERROR'.

Architecture §12.4: every Mode A pipeline event produces one root Langfuse
trace; each of the 12 steps is a child span carrying timing metadata.

Note on SDK compatibility:
    The Langfuse Python SDK ≥ 2.x uses a synchronous context manager for
    span creation (langfuse.span(...) returns a span object).  This module
    wraps that synchronous call so it is safe to use from async code.
    If a future SDK version provides a native async context manager, swap
    ``__aenter__`` / ``__aexit__`` to delegate to it directly.
"""
from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Any, Optional, Type

from src.event_pipeline.exceptions import StepTimeoutError
from src.event_pipeline.latency import StepBudget

logger = logging.getLogger(__name__)


class LangfuseSpanContext:
    """Async context manager that wraps a Langfuse child span for one pipeline step.

    On ``__aexit__``:
    - Writes ``latency_ms`` (actual elapsed ms), ``budget_ms``, ``step_name``,
      and ``sla_breach`` (bool) to the span's metadata via ``span.update()``.
    - If the exiting exception is ``StepTimeoutError``, also sets
      ``level='ERROR'`` on the span and ``sla_breach=True``.
    - Always calls ``span.end()`` to ensure the span is finalised.

    The exception is never suppressed — it always re-raises after recording.

    Args:
        parent_trace_id: Langfuse root trace ID for the current event.
        budget:          ``StepBudget`` for the step being wrapped.
        langfuse_client: Langfuse client instance.  When ``None`` (e.g. in
                         unit tests without observability), the context manager
                         is a no-op.

    Usage::

        budget = STEP_BUDGETS["classify_event"]
        async with LangfuseSpanContext(trace_id, budget, langfuse):
            async with StepLatencyGuard(budget):
                result = await classify_event(...)
    """

    def __init__(
        self,
        parent_trace_id: str,
        budget: StepBudget,
        langfuse_client: Optional[Any] = None,
    ) -> None:
        self._trace_id = parent_trace_id
        self._budget = budget
        self._langfuse = langfuse_client
        self._span: Optional[Any] = None
        self._start_ns: int = 0

    # ------------------------------------------------------------------
    # Async context manager protocol
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "LangfuseSpanContext":
        self._start_ns = time.perf_counter_ns()
        if self._langfuse is not None:
            try:
                self._span = self._langfuse.span(
                    trace_id=self._trace_id,
                    name=self._budget.step_name,
                )
            except Exception:  # pragma: no cover
                logger.warning(
                    "Failed to open Langfuse span for step '%s'",
                    self._budget.step_name,
                    exc_info=True,
                )
                self._span = None
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        elapsed_ns = time.perf_counter_ns() - self._start_ns
        latency_ms = elapsed_ns / 1_000_000.0
        is_sla_breach = isinstance(exc_val, StepTimeoutError)

        if self._span is not None:
            try:
                update_kwargs: dict[str, Any] = {
                    "metadata": {
                        "step_name": self._budget.step_name,
                        "budget_ms": self._budget.budget_ms,
                        "latency_ms": latency_ms,
                        "sla_breach": is_sla_breach,
                    }
                }
                if is_sla_breach:
                    update_kwargs["level"] = "ERROR"
                elif exc_type is not None:
                    update_kwargs["level"] = "WARNING"

                self._span.update(**update_kwargs)
            except Exception:  # pragma: no cover
                logger.warning(
                    "Failed to update Langfuse span for step '%s'",
                    self._budget.step_name,
                    exc_info=True,
                )
            finally:
                try:
                    self._span.end()
                except Exception:  # pragma: no cover
                    pass

        # Never suppress the exception.
        return False
