"""
storage.repositories.interfaces — Protocol interfaces for all storage repositories.

Each interface is a typing.Protocol so concrete implementations do not need to
inherit from an abstract base class — dependency injection works via duck typing.

Interfaces defined here:
  IWorkflowRunRepository  — PLAN-F-007 (on-demand analysis workflow)
  IAiRecommendationRepository — PLAN-F-007 TASK-010
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from src.ai.workflows.state import WorkflowState, WorkflowStatus
from src.storage.models.ai_recommendation import AiRecommendation
from src.storage.models.workflow_run import WorkflowRun


@runtime_checkable
class IWorkflowRunRepository(Protocol):
    """Repository contract for workflow_run persistence.

    All methods are tenant-scoped — every query includes tenant_id to prevent
    IDOR data leakage across tenants (Principle 3, REQ-N-006).
    """

    async def create(self, state: WorkflowState) -> WorkflowRun:
        """Insert a new workflow_run row from a WorkflowState and return the ORM model."""
        ...

    async def get(self, workflow_id: UUID, tenant_id: UUID) -> WorkflowRun | None:
        """Return the WorkflowRun by workflow_id scoped to tenant_id, or None."""
        ...

    async def update_status(
        self, workflow_id: UUID, status: WorkflowStatus, **kwargs
    ) -> None:
        """Update status (and optional kwargs like completed_at, cost_usd) for a run."""
        ...

    async def save_final_state(
        self, workflow_id: UUID, final_state: WorkflowState
    ) -> None:
        """Persist the final WorkflowState as JSONB into final_state column."""
        ...

    async def save_timeout(
        self,
        workflow_id: UUID,
        partial_state: WorkflowState,
        timeout_at: datetime,
    ) -> None:
        """Persist partial state with status=TIMEOUT when SoftTimeLimitExceeded fires.

        Sets: status='TIMEOUT', partial_result=True, timeout_at=timeout_at,
              final_state=partial_state.model_dump(), completed_at=timeout_at.

        Raises:
            WorkflowRunNotFoundError: If no row exists for workflow_id.
        """
        ...


@runtime_checkable
class IAiRecommendationRepository(Protocol):
    """Repository contract for ai_recommendation persistence.

    All methods are tenant-scoped to prevent IDOR data leakage.

    PLAN-F-007 TASK-010
    """

    async def save(self, state: WorkflowState) -> UUID:
        """Persist a recommendation from a completed WorkflowState.

        Maps WorkflowState.recommendation → ai_recommendation row.
        For on-demand runs, event_id is NULL.

        Returns:
            The recommendation_id UUID of the newly created row.
        """
        ...

    async def list_for_company(
        self,
        company_id: UUID,
        tenant_id: UUID,
        limit: int = 10,
    ) -> list[AiRecommendation]:
        """Return the most recent recommendations for a company, tenant-scoped.

        Returns:
            List of AiRecommendation ORM objects, newest first.
        """
        ...
