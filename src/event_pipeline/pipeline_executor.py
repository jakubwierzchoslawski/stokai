"""
Mode A Reactive Pipeline Executor.

PipelineExecutor runs 12 deterministic steps for every incoming geo-event.
Each step is wrapped with StepLatencyGuard (PLAN-N-001/TASK-002) to enforce
per-step latency budgets and raise StepTimeoutError on breach.

End-to-end wall-clock timing and Langfuse span integration are added in
PLAN-N-001/TASK-003 via LangfuseSpanContext.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Coroutine, Optional, TypeVar

from src.event_pipeline.exceptions import PipelineError, StepTimeoutError
from src.event_pipeline.langfuse_spans import LangfuseSpanContext
from src.event_pipeline.latency import STEP_BUDGETS, StepLatencyGuard

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Ordered list of the 12 canonical pipeline steps.
PIPELINE_STEP_ORDER: list[str] = [
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

# Wall-clock threshold for SLA warning score (10 s headroom before 90 s SLA).
_SLA_WARNING_THRESHOLD_MS: int = 80_000


class PipelineExecutor:
    """Executes the 12-step Mode A Reactive Pipeline for a single geo-event.

    Args:
        langfuse_client: Optional Langfuse client used to record spans and scores.
                         When ``None``, observability calls are skipped silently.
        trace_id:        Langfuse root trace ID for the current event.  Passed
                         through from the ingestion layer.

    Usage::

        executor = PipelineExecutor(langfuse_client=langfuse, trace_id=trace_id)
        result = await executor.run(event)
    """

    def __init__(
        self,
        langfuse_client: Optional[Any] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        self._langfuse = langfuse_client
        self._trace_id = trace_id or ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, event: dict[str, Any]) -> dict[str, Any]:
        """Execute all 12 pipeline steps in order.

        Args:
            event: Raw geo-event dict from the ingestion adapter.

        Returns:
            Pipeline result dict containing step outputs.

        Raises:
            StepTimeoutError: If any step exceeds its latency budget.
            PipelineError:    For other pipeline failures.
        """
        pipeline_start_ns = time.perf_counter_ns()
        state: dict[str, Any] = {"event": event, "steps": {}}

        try:
            # Step 1: persist_raw_event
            state["steps"]["persist_raw_event"] = await self._run_step(
                "persist_raw_event",
                self._persist_raw_event(event),
                trace_id=self._trace_id,
            )

            # Step 2: classify_event
            state["steps"]["classify_event"] = await self._run_step(
                "classify_event",
                self._classify_event(event),
                trace_id=self._trace_id,
            )

            # Step 3: extract_tickers
            state["steps"]["extract_tickers"] = await self._run_step(
                "extract_tickers",
                self._extract_tickers(event, state["steps"]["classify_event"]),
                trace_id=self._trace_id,
            )

            # Step 4: compute_exposure_map
            state["steps"]["compute_exposure_map"] = await self._run_step(
                "compute_exposure_map",
                self._compute_exposure_map(
                    event, state["steps"]["extract_tickers"]
                ),
                trace_id=self._trace_id,
            )

            # Step 5: persist_event_record
            state["steps"]["persist_event_record"] = await self._run_step(
                "persist_event_record",
                self._persist_event_record(event, state["steps"]),
                trace_id=self._trace_id,
            )

            # Step 6: embed_event
            state["steps"]["embed_event"] = await self._run_step(
                "embed_event",
                self._embed_event(event),
                trace_id=self._trace_id,
            )

            # Step 7: find_historical_analogies
            state["steps"]["find_historical_analogies"] = await self._run_step(
                "find_historical_analogies",
                self._find_historical_analogies(state["steps"]["embed_event"]),
                trace_id=self._trace_id,
            )

            # Step 8: generate_alert_text
            state["steps"]["generate_alert_text"] = await self._run_step(
                "generate_alert_text",
                self._generate_alert_text(event, state["steps"]),
                trace_id=self._trace_id,
            )

            # Step 9: evaluate_alert_rules
            state["steps"]["evaluate_alert_rules"] = await self._run_step(
                "evaluate_alert_rules",
                self._evaluate_alert_rules(event, state["steps"]),
                trace_id=self._trace_id,
            )

            # Step 10: dispatch_or_log_silent
            state["steps"]["dispatch_or_log_silent"] = await self._run_step(
                "dispatch_or_log_silent",
                self._dispatch_or_log_silent(state["steps"]),
                trace_id=self._trace_id,
            )

            # Step 11: enqueue_deep_dive
            state["steps"]["enqueue_deep_dive"] = await self._run_step(
                "enqueue_deep_dive",
                self._enqueue_deep_dive(event, state["steps"]),
                trace_id=self._trace_id,
            )

            # Step 12: return_pipeline_result
            state["steps"]["return_pipeline_result"] = await self._run_step(
                "return_pipeline_result",
                self._return_pipeline_result(state["steps"]),
                trace_id=self._trace_id,
            )

        except StepTimeoutError:
            # SLA breach: log, record observability, re-raise.
            pipeline_latency_ms = (
                time.perf_counter_ns() - pipeline_start_ns
            ) / 1_000_000.0
            self._record_pipeline_latency(pipeline_latency_ms, failed=True)
            raise
        except PipelineError:
            pipeline_latency_ms = (
                time.perf_counter_ns() - pipeline_start_ns
            ) / 1_000_000.0
            self._record_pipeline_latency(pipeline_latency_ms, failed=True)
            raise

        pipeline_latency_ms = (
            time.perf_counter_ns() - pipeline_start_ns
        ) / 1_000_000.0
        self._record_pipeline_latency(pipeline_latency_ms, failed=False)
        state["pipeline_latency_ms"] = pipeline_latency_ms
        return state

    # ------------------------------------------------------------------
    # Core step runner
    # ------------------------------------------------------------------

    async def _run_step(
        self,
        step_name: str,
        coro: Coroutine[Any, Any, T],
        *,
        trace_id: str,
    ) -> T:
        """Run a single step coroutine inside StepLatencyGuard.

        On StepTimeoutError: logs the breach at ERROR level and re-raises.
        Other exceptions propagate unchanged.

        Args:
            step_name: Canonical step identifier from PIPELINE_STEP_ORDER.
            coro:      The step coroutine to await.
            trace_id:  Langfuse root trace ID (used by LangfuseSpanContext in TASK-003).

        Returns:
            Whatever the step coroutine returns.

        Raises:
            StepTimeoutError: If the step exceeds its latency budget.
        """
        budget = STEP_BUDGETS[step_name]
        try:
            async with LangfuseSpanContext(trace_id, budget, self._langfuse):
                async with StepLatencyGuard(budget):
                    return await coro
        except StepTimeoutError as exc:
            logger.error(
                "SLA breach on step '%s': actual=%.1f ms > budget=%d ms",
                exc.step_name,
                exc.actual_ms,
                exc.budget_ms,
            )
            raise

    # ------------------------------------------------------------------
    # Observability helpers
    # ------------------------------------------------------------------

    def _record_pipeline_latency(
        self, pipeline_latency_ms: float, *, failed: bool
    ) -> None:
        """Write pipeline_latency_ms and optional sla_warning to Langfuse."""
        if self._langfuse is None:
            return
        try:
            self._langfuse.score(
                trace_id=self._trace_id,
                name="pipeline_latency_ms",
                value=pipeline_latency_ms,
            )
            if pipeline_latency_ms > _SLA_WARNING_THRESHOLD_MS:
                self._langfuse.score(
                    trace_id=self._trace_id,
                    name="sla_warning",
                    value=1,
                )
        except Exception:  # pragma: no cover
            logger.warning(
                "Failed to record pipeline_latency_ms to Langfuse", exc_info=True
            )

    # ------------------------------------------------------------------
    # Step implementations (stubs; real logic from PLAN-F-001 adapters)
    # ------------------------------------------------------------------

    async def _persist_raw_event(self, event: dict[str, Any]) -> dict[str, Any]:
        return {"raw_event_id": event.get("id", "unknown"), "status": "persisted"}

    async def _classify_event(
        self, event: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "intensity": event.get("intensity", 3),
            "category": event.get("category", "geopolitical"),
        }

    async def _extract_tickers(
        self, event: dict[str, Any], classification: dict[str, Any]
    ) -> list[str]:
        return event.get("tickers", [])

    async def _compute_exposure_map(
        self, event: dict[str, Any], tickers: list[str]
    ) -> dict[str, float]:
        return {ticker: 1.0 for ticker in tickers}

    async def _persist_event_record(
        self, event: dict[str, Any], steps: dict[str, Any]
    ) -> dict[str, Any]:
        return {"event_record_id": event.get("id", "unknown"), "status": "stored"}

    async def _embed_event(
        self, event: dict[str, Any]
    ) -> list[float]:
        return [0.0] * 128  # placeholder embedding

    async def _find_historical_analogies(
        self, embedding: list[float]
    ) -> list[dict[str, Any]]:
        return []

    async def _generate_alert_text(
        self, event: dict[str, Any], steps: dict[str, Any]
    ) -> str:
        return f"Alert: {event.get('headline', 'Event detected')}"

    async def _evaluate_alert_rules(
        self, event: dict[str, Any], steps: dict[str, Any]
    ) -> dict[str, Any]:
        return {"should_alert": True, "alert_level": "standard"}

    async def _dispatch_or_log_silent(
        self, steps: dict[str, Any]
    ) -> dict[str, Any]:
        alert_rules = steps.get("evaluate_alert_rules", {})
        if alert_rules.get("should_alert", False):
            return {"dispatched": True}
        return {"dispatched": False, "reason": "silent"}

    async def _enqueue_deep_dive(
        self, event: dict[str, Any], steps: dict[str, Any]
    ) -> dict[str, Any]:
        return {"enqueued": True, "task_id": f"deep-dive-{event.get('id', 'unknown')}"}

    async def _return_pipeline_result(
        self, steps: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "status": "completed",
            "steps_completed": len(steps),
        }
