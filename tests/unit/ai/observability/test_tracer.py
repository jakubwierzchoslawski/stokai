"""
Unit tests for LangfuseTracer.

TDD: tests written before implementation per PLAN-N-008 TASK-002.
Mocks the Langfuse Python SDK entirely — no live Langfuse server required.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.ai.observability.exceptions import SpanNotOpenError
from src.ai.observability.span_metadata import SpanMetadata
from src.ai.observability.tracer import LangfuseTracer


# ── Fixtures ────────────────────────────────────────────────────────────────


def make_metadata(**overrides) -> SpanMetadata:
    """Return a fully-populated SpanMetadata, with optional field overrides."""
    defaults = {
        "workflow_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "workflow_type": "mode_a",
        "tenant_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "user_id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "agent_role_id": "risk_analyst",
        "prompt_version": "abc123def456",
        "model_used": "claude-3-5-sonnet-20241022",
        "confidence": 0.87,
        "cost_usd": 0.0012,
        "tokens_in": 512,
        "tokens_out": 256,
        "latency_ms": 1400,
        "tools_called": ["market_data_tool"],
        "state_snapshot_ref": "snap://abc",
    }
    defaults.update(overrides)
    return SpanMetadata(**defaults)


def make_tracer() -> tuple[LangfuseTracer, MagicMock]:
    """Return (tracer, mock_langfuse_client)."""
    mock_client = MagicMock()
    tracer = LangfuseTracer(client=mock_client)
    return tracer, mock_client


# ── Tests ────────────────────────────────────────────────────────────────────


class TestOpenTrace:
    def test_open_trace_returns_trace_id(self):
        """open_trace must return a non-empty string trace_id."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-abc-123"
        mock_client.trace.return_value = mock_trace

        metadata = make_metadata()
        trace_id = tracer.open_trace(metadata)

        assert isinstance(trace_id, str)
        assert len(trace_id) > 0

    def test_open_trace_calls_sdk_trace(self):
        """open_trace must call langfuse_client.trace() exactly once."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-xyz"
        mock_client.trace.return_value = mock_trace

        tracer.open_trace(make_metadata())

        mock_client.trace.assert_called_once()

    def test_open_trace_passes_workflow_id(self):
        """open_trace passes workflow_id as trace name or metadata."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-id"
        mock_client.trace.return_value = mock_trace

        wf_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        tracer.open_trace(make_metadata(workflow_id=wf_id))

        call_kwargs = mock_client.trace.call_args[1]
        # workflow_id must appear somewhere in the call
        assert str(wf_id) in str(call_kwargs)


class TestOpenAgentSpan:
    def test_open_agent_span_uses_parent_span_id(self):
        """open_agent_span passes parent_span_id to the SDK span call."""
        tracer, mock_client = make_tracer()

        # Set up trace
        mock_trace = MagicMock()
        mock_trace.id = "trace-1"
        mock_client.trace.return_value = mock_trace

        # Set up span
        mock_span = MagicMock()
        mock_span.id = "span-child-1"
        mock_trace.span.return_value = mock_span

        metadata = make_metadata()
        tracer.open_trace(metadata)

        parent_id = "span-parent-0"
        span_id = tracer.open_agent_span("trace-1", parent_id, metadata)

        # The SDK span call must receive parent_observation_id
        call_kwargs = mock_trace.span.call_args[1]
        assert call_kwargs.get("parent_observation_id") == parent_id

    def test_open_agent_span_returns_span_id(self):
        """open_agent_span returns the span_id string."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-2"
        mock_client.trace.return_value = mock_trace

        mock_span = MagicMock()
        mock_span.id = "span-42"
        mock_trace.span.return_value = mock_span

        metadata = make_metadata()
        tracer.open_trace(metadata)
        span_id = tracer.open_agent_span("trace-2", None, metadata)

        assert span_id == "span-42"


class TestCloseAgentSpan:
    def test_close_agent_span_flushes_metadata(self):
        """close_agent_span calls span.update(metadata=...) with required fields."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-3"
        mock_client.trace.return_value = mock_trace

        mock_span = MagicMock()
        mock_span.id = "span-3"
        mock_trace.span.return_value = mock_span

        metadata = make_metadata()
        tracer.open_trace(metadata)
        span_id = tracer.open_agent_span("trace-3", None, metadata)

        output_meta = make_metadata(
            tokens_in=100,
            tokens_out=200,
            cost_usd=0.005,
            confidence=0.95,
            latency_ms=1000,
        )
        tracer.close_agent_span(span_id, output_meta)

        mock_span.update.assert_called_once()
        update_kwargs = mock_span.update.call_args[1]
        # metadata key must be present
        assert "metadata" in update_kwargs
        span_meta = update_kwargs["metadata"]
        assert span_meta.get("tokens_in") == 100
        assert span_meta.get("tokens_out") == 200
        assert span_meta.get("cost_usd") == 0.005
        assert span_meta.get("confidence") == 0.95

    def test_span_not_open_error(self):
        """close_agent_span raises SpanNotOpenError when span_id is unknown."""
        tracer, _ = make_tracer()

        with pytest.raises(SpanNotOpenError):
            tracer.close_agent_span("nonexistent-span-id", make_metadata())


class TestOpenToolSpan:
    def test_open_tool_span_sets_tool_name(self):
        """open_tool_span passes tool_name as span name."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-4"
        mock_client.trace.return_value = mock_trace

        mock_span = MagicMock()
        mock_span.id = "tool-span-1"
        mock_trace.span.return_value = mock_span

        metadata = make_metadata()
        tracer.open_trace(metadata)

        tracer.open_tool_span(
            trace_id="trace-4",
            parent_span_id="span-parent",
            tool_name="market_data_tool",
            args_hash="abc123",
            cached=False,
        )

        call_kwargs = mock_trace.span.call_args[1]
        assert call_kwargs.get("name") == "market_data_tool"

    def test_open_tool_span_records_cached_flag(self):
        """open_tool_span stores cached flag in span metadata."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-5"
        mock_client.trace.return_value = mock_trace

        mock_span = MagicMock()
        mock_span.id = "tool-span-2"
        mock_trace.span.return_value = mock_span

        metadata = make_metadata()
        tracer.open_trace(metadata)

        tracer.open_tool_span(
            trace_id="trace-5",
            parent_span_id="span-parent",
            tool_name="search_tool",
            args_hash="def456",
            cached=True,
        )

        call_kwargs = mock_trace.span.call_args[1]
        span_meta = call_kwargs.get("metadata", {})
        assert span_meta.get("cached") is True


class TestCloseTrace:
    def test_close_trace_flushes_cost(self):
        """close_trace calls trace.update with cost_usd and client.flush()."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-6"
        mock_client.trace.return_value = mock_trace

        metadata = make_metadata()
        tracer.open_trace(metadata)

        tracer.close_trace("trace-6", cost_usd=0.0123)

        mock_trace.update.assert_called_once()
        update_kwargs = mock_trace.update.call_args[1]
        assert update_kwargs.get("metadata", {}).get("cost_usd") == 0.0123

        mock_client.flush.assert_called_once()


class TestCloseToolSpan:
    def test_close_tool_span_updates_span(self):
        """close_tool_span calls span.update with result_rows and latency_ms."""
        tracer, mock_client = make_tracer()

        mock_trace = MagicMock()
        mock_trace.id = "trace-7"
        mock_client.trace.return_value = mock_trace

        mock_span = MagicMock()
        mock_span.id = "tool-span-3"
        mock_trace.span.return_value = mock_span

        metadata = make_metadata()
        tracer.open_trace(metadata)
        span_id = tracer.open_tool_span(
            trace_id="trace-7",
            parent_span_id="span-parent",
            tool_name="data_tool",
            args_hash="xyz",
            cached=False,
        )

        tracer.close_tool_span(span_id, result_rows=10, latency_ms=250, error_type=None)

        mock_span.update.assert_called_once()
        call_kwargs = mock_span.update.call_args[1]
        meta = call_kwargs.get("metadata", {})
        assert meta.get("result_rows") == 10
        assert meta.get("latency_ms") == 250
