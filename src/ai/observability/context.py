"""
WorkflowTracingContext — asyncio-safe propagation of active trace/span IDs.

Uses contextvars.ContextVar so that concurrent async workflow executions each
carry their own (trace_id, span_id) without shared mutable state.

Usage::

    ctx = WorkflowTracingContext()
    token = ctx.set_current("trace-123", "span-456")
    ...
    trace_id, span_id = ctx.get_current()
    ...
    ctx.reset(token)
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass(frozen=True)
class _TracingState:
    trace_id: str
    span_id: str | None


class WorkflowTracingContext:
    """Thread- and async-safe holder for the active trace_id and span_id."""

    def __init__(self) -> None:
        self._var: contextvars.ContextVar[_TracingState | None] = (
            contextvars.ContextVar("workflow_tracing_context", default=None)
        )

    def set_current(
        self,
        trace_id: str,
        span_id: str | None = None,
    ) -> contextvars.Token[_TracingState | None]:
        """Set the current tracing state; returns a Token for later reset."""
        return self._var.set(_TracingState(trace_id=trace_id, span_id=span_id))

    def get_current(self) -> tuple[str | None, str | None]:
        """Return (trace_id, span_id) for the current async context, or (None, None)."""
        state = self._var.get()
        if state is None:
            return None, None
        return state.trace_id, state.span_id

    def reset(self, token: contextvars.Token) -> None:
        """Restore the previous tracing state using the token from set_current."""
        self._var.reset(token)


# Module-level singleton — injected into node_executor and base_workflow
workflow_tracing_context = WorkflowTracingContext()
