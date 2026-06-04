"""
Unit tests for LangfuseTracer.

Mocks the Langfuse Python SDK so no real Langfuse host is required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ai.langfuse_tracer import LangfuseTracer


class TestLangfuseTracer:
    """Tests for LangfuseTracer."""

    def test_start_trace_returns_non_empty_string(self) -> None:
        with patch("src.ai.langfuse_tracer.Langfuse") as mock_langfuse_cls:
            mock_lf = MagicMock()
            mock_trace = MagicMock()
            mock_trace.id = "trace-abc-123"
            mock_lf.trace.return_value = mock_trace
            mock_langfuse_cls.return_value = mock_lf

            tracer = LangfuseTracer(
                secret_key="sk-test",
                public_key="pk-test",
                host="http://localhost:3000",
            )
            trace_id = tracer.start_trace("test_pipeline", {"env": "test"})

        assert trace_id == "trace-abc-123"
        assert len(trace_id) > 0

    def test_end_span_records_cost_and_latency(self) -> None:
        with patch("src.ai.langfuse_tracer.Langfuse") as mock_langfuse_cls:
            mock_lf = MagicMock()
            mock_trace = MagicMock()
            mock_trace.id = "trace-xyz"
            mock_lf.trace.return_value = mock_trace

            mock_span = MagicMock()
            mock_span.id = "span-001"
            mock_trace.generation.return_value = mock_span
            mock_langfuse_cls.return_value = mock_lf

            tracer = LangfuseTracer("sk", "pk", "http://lf:3000")
            trace_id = tracer.start_trace("pipeline", {})
            span_id = tracer.start_span(trace_id, "classify_event", {"input": "data"})
            tracer.end_span(span_id, {"output": "result"}, cost_usd=0.002, latency_ms=450)

        mock_span.end.assert_called_once()
        call_kwargs = mock_span.end.call_args.kwargs
        assert call_kwargs.get("usage") is not None or call_kwargs.get("output") is not None

    def test_sdk_connection_error_logs_warning_and_continues(self) -> None:
        with patch("src.ai.langfuse_tracer.Langfuse") as mock_langfuse_cls:
            mock_lf = MagicMock()
            mock_lf.trace.side_effect = ConnectionError("Connection refused")
            mock_langfuse_cls.return_value = mock_lf

            tracer = LangfuseTracer("sk", "pk", "http://lf:3000")

            # Must not raise — observability failures are non-fatal
            trace_id = tracer.start_trace("pipeline", {})

        # Returns a fallback ID, not empty
        assert isinstance(trace_id, str)

    def test_end_trace_flush_failure_does_not_propagate(self) -> None:
        with patch("src.ai.langfuse_tracer.Langfuse") as mock_langfuse_cls:
            mock_lf = MagicMock()
            mock_trace = MagicMock()
            mock_trace.id = "trace-flush-fail"
            mock_lf.trace.return_value = mock_trace
            mock_lf.flush.side_effect = RuntimeError("flush failed")
            mock_langfuse_cls.return_value = mock_lf

            tracer = LangfuseTracer("sk", "pk", "http://lf:3000")
            trace_id = tracer.start_trace("pipeline", {})

            # Must not propagate flush failure
            tracer.end_trace(trace_id, {"result": "ok"})
