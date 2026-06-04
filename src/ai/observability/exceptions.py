"""
Exceptions for the AI observability layer.

Raised when the LangfuseTracer contract is violated (e.g. closing a span
that was never opened).
"""
from __future__ import annotations


class TracerError(Exception):
    """Base class for all tracer errors."""


class SpanNotOpenError(TracerError):
    """Raised when close_agent_span or close_tool_span is called for an unknown span_id."""

    def __init__(self, span_id: str) -> None:
        super().__init__(
            f"No open span with id={span_id!r}. "
            "open_agent_span / open_tool_span must be called first."
        )
        self.span_id = span_id
