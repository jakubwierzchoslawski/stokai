"""
BaseWorkflow — lifecycle management for LangGraph-based workflow runs.

Architecture §7.1: Langfuse trace opened at workflow entry, closed at exit.
The langfuse_trace_id is stored on the workflow_run row via the episodic
repository (cross-link between PostgreSQL and Langfuse, Architecture §10).

Subclasses must implement _execute(state) with the actual node graph.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from src.ai.observability.span_metadata import SpanMetadata
from src.ai.observability.tracer import ILangfuseTracer

logger = logging.getLogger(__name__)


class WorkflowState:
    """Minimal mutable workflow state passed through all nodes.

    Subclasses add domain-specific fields (event data, scores, etc.).
    """

    def __init__(
        self,
        workflow_id: Any,
        workflow_type: str,
        tenant_id: Any,
        user_id: Any,
    ) -> None:
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.trace_id: str | None = None
        self.cost_usd: float = 0.0


class BaseWorkflow(ABC):
    """Abstract base for all StokAI workflows.

    Parameters
    ----------
    tracer:
        ILangfuseTracer implementation.
    episodic_repo:
        Repository with update_workflow_run_trace_id; persists langfuse_trace_id.
    """

    def __init__(
        self,
        tracer: ILangfuseTracer,
        episodic_repo: Any,
    ) -> None:
        self._tracer = tracer
        self._episodic_repo = episodic_repo

    async def run(self, state: Any) -> Any:
        """Run the full workflow: open trace → execute → close trace.

        Opens a Langfuse trace, stores trace_id on state, delegates to
        _execute(), closes the trace and persists langfuse_trace_id to the
        workflow_run row.
        """
        root_metadata = SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            agent_role_id=None,
            prompt_version=None,
            model_used=None,
            confidence=None,
            cost_usd=None,
            tokens_in=None,
            tokens_out=None,
            latency_ms=None,
            tools_called=None,
            state_snapshot_ref=None,
        )

        trace_id = self._tracer.open_trace(root_metadata)
        state.trace_id = trace_id
        logger.debug("Workflow %s started, trace_id=%s", state.workflow_id, trace_id)

        try:
            state = await self._execute(state)
        finally:
            self._tracer.close_trace(trace_id, cost_usd=getattr(state, "cost_usd", 0.0))
            logger.debug("Workflow %s finished, trace_id=%s", state.workflow_id, trace_id)

            # Authoritative cross-link: persist trace_id to PostgreSQL
            await self._episodic_repo.update_workflow_run_trace_id(
                workflow_run_id=state.workflow_id,
                trace_id=trace_id,
            )

        return state

    @abstractmethod
    async def _execute(self, state: Any) -> Any:
        """Implement the actual node graph execution."""
