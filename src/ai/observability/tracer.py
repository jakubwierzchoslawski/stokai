"""
LangfuseTracer — sole point in the system that calls the Langfuse Python SDK.

Architecture §12.4: every workflow run produces one Langfuse trace with child
spans for agent invocations and tool calls.

Design decisions:
- ILangfuseTracer is a Protocol (structural subtyping) so tests can inject
  a mock without inheriting from a concrete class.
- LangfuseTracer is injected via constructor; callers never import langfuse
  directly.
- Internal span registry maps span_id → SDK span object.  SpanNotOpenError
  is raised when close_* is called for an unknown span_id.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from src.ai.observability.exceptions import SpanNotOpenError
from src.ai.observability.span_metadata import SpanMetadata

logger = logging.getLogger(__name__)


# ── Protocol (interface) ─────────────────────────────────────────────────────


@runtime_checkable
class ILangfuseTracer(Protocol):
    """Structural interface for the Langfuse tracer.

    Depend on this protocol rather than LangfuseTracer directly (DIP).
    """

    def open_trace(self, metadata: SpanMetadata) -> str:
        """Open a new workflow-level trace. Returns the trace_id string."""
        ...

    def open_agent_span(
        self,
        trace_id: str,
        parent_span_id: str | None,
        metadata: SpanMetadata,
    ) -> str:
        """Open an agent invocation span under the given trace. Returns span_id."""
        ...

    def close_agent_span(self, span_id: str, output_metadata: SpanMetadata) -> None:
        """Close an agent span, flushing output metadata to Langfuse."""
        ...

    def open_tool_span(
        self,
        trace_id: str,
        parent_span_id: str | None,
        tool_name: str,
        args_hash: str,
        cached: bool,
    ) -> str:
        """Open a tool-call span under the given trace. Returns span_id."""
        ...

    def close_tool_span(
        self,
        span_id: str,
        result_rows: int,
        latency_ms: int,
        error_type: str | None,
    ) -> None:
        """Close a tool span, recording result_rows, latency, and optional error."""
        ...

    def close_trace(self, trace_id: str, cost_usd: float) -> None:
        """Close the workflow-level trace and flush the SDK queue."""
        ...


# ── Concrete implementation ──────────────────────────────────────────────────


class LangfuseTracer:
    """Concrete Langfuse tracer.

    Parameters
    ----------
    client:
        A ``langfuse.Langfuse`` instance (or any compatible mock).
        When omitted the tracer constructs its own client from Settings.
    """

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from langfuse import Langfuse  # type: ignore[import]

            from src.config.settings import get_settings

            settings = get_settings()
            client = Langfuse(
                secret_key=settings.LANGFUSE_SECRET_KEY,
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                host=settings.LANGFUSE_HOST,
            )
        self._client = client
        # span_id → SDK span object
        self._open_spans: dict[str, Any] = {}
        # trace_id → SDK trace object
        self._open_traces: dict[str, Any] = {}

    # ── Trace lifecycle ──────────────────────────────────────────────────────

    def open_trace(self, metadata: SpanMetadata) -> str:
        """Open a new workflow-level Langfuse trace. Returns trace_id."""
        sdk_meta = metadata.to_langfuse_metadata()
        trace = self._client.trace(
            name=f"{metadata.workflow_type}:{metadata.workflow_id}",
            user_id=str(metadata.user_id),
            metadata=sdk_meta,
        )
        trace_id: str = trace.id
        self._open_traces[trace_id] = trace
        logger.debug("Opened Langfuse trace %s for workflow %s", trace_id, metadata.workflow_id)
        return trace_id

    def close_trace(self, trace_id: str, cost_usd: float) -> None:
        """Close the workflow-level trace and flush the SDK queue."""
        trace = self._open_traces.pop(trace_id, None)
        if trace is not None:
            trace.update(metadata={"cost_usd": cost_usd})
        else:
            logger.warning("close_trace called for unknown trace_id=%s", trace_id)
        self._client.flush()
        logger.debug("Closed Langfuse trace %s (cost_usd=%s)", trace_id, cost_usd)

    # ── Agent span lifecycle ─────────────────────────────────────────────────

    def open_agent_span(
        self,
        trace_id: str,
        parent_span_id: str | None,
        metadata: SpanMetadata,
    ) -> str:
        """Open an agent invocation span. Returns span_id."""
        trace = self._open_traces.get(trace_id)
        if trace is None:
            # Reconstruct a lightweight trace reference for late-bound spans
            trace = self._client.trace(id=trace_id)

        sdk_meta = metadata.to_langfuse_metadata()
        span = trace.span(
            name=metadata.agent_role_id or "agent",
            parent_observation_id=parent_span_id,
            metadata=sdk_meta,
        )
        span_id: str = span.id
        self._open_spans[span_id] = span
        logger.debug(
            "Opened agent span %s (parent=%s) on trace %s", span_id, parent_span_id, trace_id
        )
        return span_id

    def close_agent_span(self, span_id: str, output_metadata: SpanMetadata) -> None:
        """Close an agent span, flushing output metadata to Langfuse."""
        span = self._open_spans.pop(span_id, None)
        if span is None:
            raise SpanNotOpenError(span_id)

        sdk_meta = output_metadata.to_langfuse_metadata()
        span.update(metadata=sdk_meta)
        logger.debug("Closed agent span %s", span_id)

    # ── Tool span lifecycle ──────────────────────────────────────────────────

    def open_tool_span(
        self,
        trace_id: str,
        parent_span_id: str | None,
        tool_name: str,
        args_hash: str,
        cached: bool,
    ) -> str:
        """Open a tool-call span. Returns span_id."""
        trace = self._open_traces.get(trace_id)
        if trace is None:
            trace = self._client.trace(id=trace_id)

        span = trace.span(
            name=tool_name,
            parent_observation_id=parent_span_id,
            metadata={"args_hash": args_hash, "cached": cached},
        )
        span_id: str = span.id
        self._open_spans[span_id] = span
        logger.debug(
            "Opened tool span %s name=%r (cached=%s) on trace %s",
            span_id,
            tool_name,
            cached,
            trace_id,
        )
        return span_id

    def close_tool_span(
        self,
        span_id: str,
        result_rows: int,
        latency_ms: int,
        error_type: str | None,
    ) -> None:
        """Close a tool span, recording result statistics."""
        span = self._open_spans.pop(span_id, None)
        if span is None:
            raise SpanNotOpenError(span_id)

        meta: dict[str, Any] = {"result_rows": result_rows, "latency_ms": latency_ms}
        if error_type is not None:
            meta["error_type"] = error_type

        span.update(metadata=meta)
        logger.debug("Closed tool span %s (result_rows=%s)", span_id, result_rows)
