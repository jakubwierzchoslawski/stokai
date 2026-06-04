"""
IEpisodicRepository — abstract interface for Layer 1 episodic memory operations.

All write operations are INSERT-only; the append-only constraint is enforced
at the DB level (triggers in migration 0033).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocation,
    AgentInvocationCreate,
    RecommendationOutcome,
    RecommendationOutcomeCreate,
    ToolCall,
    ToolCallCreate,
    WorkflowRun,
    WorkflowRunCreate,
)


class IEpisodicRepository(ABC):
    """Abstract repository for Layer 1 episodic memory."""

    @abstractmethod
    async def append_workflow_run(self, run: WorkflowRunCreate) -> WorkflowRun:
        """Insert a new workflow run row and return the created entity."""
        ...

    @abstractmethod
    async def append_agent_invocation(
        self, inv: AgentInvocationCreate
    ) -> AgentInvocation:
        """Insert a new agent invocation row and return the created entity."""
        ...

    @abstractmethod
    async def append_tool_call(self, call: ToolCallCreate) -> ToolCall:
        """Insert a new tool call row and return the created entity."""
        ...

    @abstractmethod
    async def append_recommendation_outcome(
        self, outcome: RecommendationOutcomeCreate
    ) -> RecommendationOutcome:
        """Insert a new recommendation outcome row and return the created entity."""
        ...

    @abstractmethod
    async def fill_outcome_actuals(
        self,
        rec_id: UUID,
        actual_t1d: float,
        actual_t1w: float,
        direction_correct: bool,
    ) -> None:
        """
        Update the calibration columns on a recommendation_outcome row.

        Only actual_t1d, actual_t1w, direction_correct, and filled_at are updated.
        All other columns remain unchanged.
        """
        ...

    @abstractmethod
    async def get_workflow_run(self, workflow_id: UUID) -> WorkflowRun | None:
        """Retrieve a single workflow run by its ID, or None if not found."""
        ...

    @abstractmethod
    async def list_recent_runs(
        self, tenant_id: UUID, limit: int = 50
    ) -> list[WorkflowRun]:
        """
        Return the most recent workflow runs for a tenant.

        Results are ordered by started_at descending, bounded by limit.
        """
        ...

    @abstractmethod
    async def list_outcomes_by_date(
        self, reference_date: date
    ) -> list[RecommendationOutcome]:
        """
        Return recommendation_outcome rows where created_at::date = reference_date
        and filled_at IS NOT NULL.

        Used by Tier3CalibrationService to compute daily calibration metrics.
        """
        ...
