"""
ai.workflows.tracer — LangfuseWorkflowTracer context manager.

Opens a root Langfuse trace on __enter__ and closes it on __exit__.
Records workflow_id, workflow_type, tenant_id, user_id, started_at in the trace.
Stores the trace_id in state.langfuse_trace_id.

No-op when the Langfuse client is None (LANGFUSE_HOST not set or client is None).
Langfuse exceptions are swallowed — observability must never break the workflow.
"""
from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

from src.ai.workflows.state import WorkflowState

logger = logging.getLogger(__name__)


class LangfuseWorkflowTracer:
    """Context manager that wraps a workflow run in a Langfuse root trace.

    Usage::

        tracer = LangfuseWorkflowTracer(state=state, client=langfuse_client)
        with tracer:
            ...  # workflow nodes execute here
            # state.langfuse_trace_id is set inside the block

    Args:
        state: The WorkflowState for this run (mutated in-place on __enter__
               to set langfuse_trace_id).
        client: An initialised Langfuse client, or None to no-op.
    """

    def __init__(self, state: WorkflowState, client: Any | None) -> None:
        self._state = state
        self._client = client
        self._trace: Any | None = None

    def __enter__(self) -> "LangfuseWorkflowTracer":
        if self._client is None:
            return self

        try:
            self._trace = self._client.trace(
                id=str(self._state.workflow_id),
                name=f"workflow:{self._state.workflow_type.value}",
                metadata={
                    "workflow_id": str(self._state.workflow_id),
                    "workflow_type": self._state.workflow_type.value,
                    "tenant_id": str(self._state.tenant_id),
                    "user_id": str(self._state.user_id),
                    "started_at": self._state.started_at.isoformat(),
                },
            )
            # Set trace_id on the mutable state object
            self._state.langfuse_trace_id = self._trace.id
        except Exception:
            logger.exception(
                "LangfuseWorkflowTracer: failed to open trace for workflow=%s",
                self._state.workflow_id,
            )
            self._trace = None

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._trace is None:
            return

        try:
            self._trace.update(
                output={
                    "status": self._state.status.value,
                    "cost_usd": self._state.cost_usd,
                    "tokens_consumed": self._state.tokens_consumed,
                }
            )
        except Exception:
            logger.exception(
                "LangfuseWorkflowTracer: failed to close trace for workflow=%s",
                self._state.workflow_id,
            )
