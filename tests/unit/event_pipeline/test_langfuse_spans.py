"""
Unit tests for LangfuseSpanContext and PipelineExecutor Langfuse integration.

TDD test suite for TASK-003 (PLAN-N-001).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.event_pipeline.exceptions import StepTimeoutError
from src.event_pipeline.langfuse_spans import LangfuseSpanContext
from src.event_pipeline.latency import STEP_BUDGETS, StepBudget
from src.event_pipeline.pipeline_executor import PipelineExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_budget(
    step_name: str = "classify_event",
    budget_ms: int = 5_000,
    is_llm: bool = True,
) -> StepBudget:
    return StepBudget(step_name=step_name, budget_ms=budget_ms, is_llm=is_llm)


def make_mock_langfuse_client():
    """Build a mock Langfuse client with span() and score() methods."""
    client = MagicMock()
    mock_span = MagicMock()
    mock_span.update = MagicMock()
    mock_span.end = MagicMock()
    # span() returns the mock span object directly (synchronous SDK)
    client.span.return_value = mock_span
    client.score = MagicMock()
    return client, mock_span


# ---------------------------------------------------------------------------
# LangfuseSpanContext unit tests
# ---------------------------------------------------------------------------


class TestLangfuseSpanContext:
    """Tests for the LangfuseSpanContext async context manager."""

    @pytest.mark.asyncio
    async def test_langfuse_span_context_happy_path_writes_latency_ms(self):
        """Happy path: __aexit__ writes latency_ms > 0 and sla_breach=False to span."""
        langfuse_client, mock_span = make_mock_langfuse_client()
        budget = make_budget(step_name="classify_event", budget_ms=5_000)

        ctx = LangfuseSpanContext(
            parent_trace_id="trace-abc",
            budget=budget,
            langfuse_client=langfuse_client,
        )
        async with ctx:
            await asyncio.sleep(0.01)  # 10 ms — well within budget

        # span() was called to open the span
        langfuse_client.span.assert_called_once()
        # update() was called with metadata including latency_ms
        mock_span.update.assert_called()
        update_kwargs = mock_span.update.call_args.kwargs
        # latency_ms should be > 0
        assert update_kwargs.get("metadata", {}).get("latency_ms", 0) > 0
        assert update_kwargs.get("metadata", {}).get("sla_breach") is False
        assert update_kwargs.get("metadata", {}).get("step_name") == "classify_event"
        assert update_kwargs.get("metadata", {}).get("budget_ms") == 5_000

    @pytest.mark.asyncio
    async def test_langfuse_span_context_timeout_error_marks_span_error(self):
        """When StepTimeoutError is raised inside the context, span gets status='error'."""
        langfuse_client, mock_span = make_mock_langfuse_client()
        budget = make_budget(step_name="classify_event", budget_ms=5_000)

        ctx = LangfuseSpanContext(
            parent_trace_id="trace-xyz",
            budget=budget,
            langfuse_client=langfuse_client,
        )

        with pytest.raises(StepTimeoutError):
            async with ctx:
                raise StepTimeoutError(
                    step_name="classify_event",
                    budget_ms=5_000,
                    actual_ms=6_100.0,
                )

        # span must be marked as error
        mock_span.update.assert_called()
        update_kwargs = mock_span.update.call_args.kwargs
        assert update_kwargs.get("level") == "ERROR"
        meta = update_kwargs.get("metadata", {})
        assert meta.get("sla_breach") is True

    @pytest.mark.asyncio
    async def test_non_timeout_error_propagates_without_marking_sla_breach(self):
        """A generic ValueError should propagate; sla_breach must not be set True."""
        langfuse_client, mock_span = make_mock_langfuse_client()
        budget = make_budget()

        ctx = LangfuseSpanContext(
            parent_trace_id="trace-err",
            budget=budget,
            langfuse_client=langfuse_client,
        )

        with pytest.raises(ValueError, match="boom"):
            async with ctx:
                raise ValueError("boom")

        # Span update should still be called, but sla_breach=False
        mock_span.update.assert_called()
        update_kwargs = mock_span.update.call_args.kwargs
        meta = update_kwargs.get("metadata", {})
        assert meta.get("sla_breach") is False

    @pytest.mark.asyncio
    async def test_span_end_always_called(self):
        """span.end() must always be called on __aexit__ (happy path)."""
        langfuse_client, mock_span = make_mock_langfuse_client()
        budget = make_budget()

        async with LangfuseSpanContext(
            parent_trace_id="trace-end",
            budget=budget,
            langfuse_client=langfuse_client,
        ):
            pass

        mock_span.end.assert_called_once()

    @pytest.mark.asyncio
    async def test_span_end_called_on_exception(self):
        """span.end() must always be called on __aexit__ even when an exception occurs."""
        langfuse_client, mock_span = make_mock_langfuse_client()
        budget = make_budget()

        with pytest.raises(RuntimeError):
            async with LangfuseSpanContext(
                parent_trace_id="trace-end-exc",
                budget=budget,
                langfuse_client=langfuse_client,
            ):
                raise RuntimeError("unexpected failure")

        mock_span.end.assert_called_once()


# ---------------------------------------------------------------------------
# PipelineExecutor + Langfuse integration tests
# ---------------------------------------------------------------------------


def _make_event(event_id: str = "evt-001", intensity: int = 4) -> dict:
    return {
        "id": event_id,
        "headline": "Test event",
        "intensity": intensity,
        "source": "gdelt",
        "tickers": ["AAPL"],
    }


class TestPipelineExecutorLangfuseIntegration:
    """Tests for PipelineExecutor Langfuse score recording."""

    @pytest.mark.asyncio
    async def test_pipeline_executor_writes_pipeline_latency_ms_score(self):
        """After a successful run, pipeline_latency_ms score must be written to Langfuse."""
        langfuse_client, _ = make_mock_langfuse_client()

        executor = PipelineExecutor(
            langfuse_client=langfuse_client,
            trace_id="trace-pipeline-latency",
        )
        event = _make_event()
        result = await executor.run(event)

        # Verify the score was recorded
        langfuse_client.score.assert_called()
        # Find the call for pipeline_latency_ms
        score_calls = langfuse_client.score.call_args_list
        latency_call = next(
            (c for c in score_calls if c.kwargs.get("name") == "pipeline_latency_ms"),
            None,
        )
        assert latency_call is not None, "pipeline_latency_ms score not recorded"
        assert latency_call.kwargs["trace_id"] == "trace-pipeline-latency"
        assert latency_call.kwargs["value"] > 0

    @pytest.mark.asyncio
    async def test_pipeline_executor_writes_sla_warning_when_over_80s(self):
        """
        When total pipeline latency exceeds 80 000 ms, an sla_warning=1 score
        must be written to Langfuse on the root trace.
        """
        langfuse_client, _ = make_mock_langfuse_client()

        executor = PipelineExecutor(
            langfuse_client=langfuse_client,
            trace_id="trace-sla-warning",
        )

        # Patch _record_pipeline_latency to simulate > 80 s scenario.
        with patch.object(
            executor,
            "_record_pipeline_latency",
            wraps=lambda latency_ms, **kw: executor._record_pipeline_latency_direct(
                80_001.0, failed=False
            ),
        ):
            pass  # we call the real method below directly

        # Call _record_pipeline_latency directly with 80 001 ms to test logic.
        executor._record_pipeline_latency(80_001.0, failed=False)

        score_calls = langfuse_client.score.call_args_list
        sla_call = next(
            (c for c in score_calls if c.kwargs.get("name") == "sla_warning"),
            None,
        )
        assert sla_call is not None, "sla_warning score not recorded for > 80 s latency"
        assert sla_call.kwargs["value"] == 1

    @pytest.mark.asyncio
    async def test_pipeline_result_contains_pipeline_latency_ms(self):
        """The result dict from executor.run() must include pipeline_latency_ms."""
        executor = PipelineExecutor()
        result = await executor.run(_make_event())
        assert "pipeline_latency_ms" in result
        assert result["pipeline_latency_ms"] > 0

    @pytest.mark.asyncio
    async def test_pipeline_executor_no_langfuse_client_does_not_raise(self):
        """When langfuse_client is None, run() completes without error."""
        executor = PipelineExecutor(langfuse_client=None)
        result = await executor.run(_make_event())
        assert result is not None
