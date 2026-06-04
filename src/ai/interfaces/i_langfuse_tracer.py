"""
ILangfuseTracer — protocol for Langfuse observability integration.
"""
from __future__ import annotations

from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class ILangfuseTracer(Protocol):
    """Interface for creating and managing Langfuse traces and spans.

    One trace is created per pipeline run; each LLM/embedding call is a child
    span of that trace.  Implementations must never raise — Langfuse failures
    are non-fatal.
    """

    def start_trace(self, name: str, metadata: dict) -> str:
        """Create a new root trace and return its ID.

        Args:
            name: Human-readable trace name.
            metadata: Arbitrary key-value pairs attached to the trace.

        Returns:
            Trace ID string (non-empty on success; may return sentinel on failure).
        """
        ...

    def start_span(self, trace_id: str, name: str, input: dict) -> str:
        """Create a child generation span under *trace_id*.

        Args:
            trace_id: Parent trace identifier.
            name: Span name (e.g. "classify_event").
            input: Input data recorded on the span.

        Returns:
            Span ID string.
        """
        ...

    def end_span(
        self,
        span_id: str,
        output: dict,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        """Close a span, recording its output and performance metrics.

        Args:
            span_id: The span to close.
            output: Output data recorded on the span.
            cost_usd: Monetary cost attributed to this span.
            latency_ms: Wall-clock duration of the span in milliseconds.
        """
        ...

    def end_trace(self, trace_id: str, output: dict) -> None:
        """Flush and close the root trace.

        Args:
            trace_id: The trace to close.
            output: Final output summary attached to the trace.
        """
        ...
