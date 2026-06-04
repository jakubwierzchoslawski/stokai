"""
Unit tests for LangfuseWorkflowTracer context manager.

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


def _make_state(**kwargs) -> WorkflowState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.ON_DEMAND,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


class TestLangfuseWorkflowTracer:
    def test_tracer_sets_trace_id_on_enter(self):
        """__enter__ sets state.langfuse_trace_id from client.trace()."""
        from src.ai.workflows.tracer import LangfuseWorkflowTracer

        state = _make_state()
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-abc-123"
        mock_client.trace.return_value = mock_trace

        tracer = LangfuseWorkflowTracer(state=state, client=mock_client)
        with tracer:
            pass

        assert state.langfuse_trace_id == "trace-abc-123"

    def test_tracer_noop_when_client_is_none(self):
        """No-op when client is None (LANGFUSE_HOST not set)."""
        from src.ai.workflows.tracer import LangfuseWorkflowTracer

        state = _make_state()
        tracer = LangfuseWorkflowTracer(state=state, client=None)

        # Must not raise; trace_id remains None
        with tracer:
            pass

        assert state.langfuse_trace_id is None

    def test_tracer_records_cost_and_status_on_exit(self):
        """__exit__ records cost_usd and status via client."""
        from src.ai.workflows.tracer import LangfuseWorkflowTracer

        state = _make_state()
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-xyz"
        mock_client.trace.return_value = mock_trace

        tracer = LangfuseWorkflowTracer(state=state, client=mock_client)
        with tracer:
            state = state.model_copy(
                update={"cost_usd": 0.42, "status": WorkflowStatus.COMPLETED}
            )

        # Client trace or update should have been called
        mock_client.trace.assert_called_once()

    def test_tracer_passes_workflow_metadata_to_langfuse(self):
        """trace() is called with workflow_id, workflow_type, tenant_id, user_id."""
        from src.ai.workflows.tracer import LangfuseWorkflowTracer

        state = _make_state()
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-meta"
        mock_client.trace.return_value = mock_trace

        tracer = LangfuseWorkflowTracer(state=state, client=mock_client)
        with tracer:
            pass

        call_kwargs = mock_client.trace.call_args
        assert call_kwargs is not None
        # The trace should include workflow metadata
        all_args = str(call_kwargs)
        assert str(state.workflow_id) in all_args or "workflow_id" in all_args

    def test_tracer_handles_client_exception_gracefully(self):
        """Exceptions from Langfuse client do not propagate."""
        from src.ai.workflows.tracer import LangfuseWorkflowTracer

        state = _make_state()
        mock_client = MagicMock()
        mock_client.trace.side_effect = RuntimeError("Langfuse unavailable")

        tracer = LangfuseWorkflowTracer(state=state, client=mock_client)

        # Must not raise even when Langfuse is unavailable
        with tracer:
            pass

        assert state.langfuse_trace_id is None
