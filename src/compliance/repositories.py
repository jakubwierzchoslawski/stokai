"""
compliance.repositories — SQLAlchemy 2.0 async implementations of compliance
repository interfaces.

SqlComplianceRepository: queries workflow_run and agent_invocation tables.
SqlRecommendationRepository: queries ai_recommendation and recommendation_outcome.

These are read-only repositories; they perform no writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.models.episodic_models import (
    AgentInvocation as AgentInvocationORM,
    RecommendationOutcome as RecommendationOutcomeORM,
    WorkflowRun as WorkflowRunORM,
)
from src.compliance.compliance_check_service import (
    IComplianceRepository,
    IRecommendationRepository,
    RecommendationWithOutcome,
    WorkflowRunSummary,
)

# Status values considered "completed" for the coverage check.
_COMPLETED_STATUSES = ("done", "failed", "completed")


class SqlComplianceRepository(IComplianceRepository):
    """SQLAlchemy implementation of IComplianceRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_completed_runs_in_window(
        self, lookback_days: int
    ) -> list[WorkflowRunSummary]:
        """Return completed workflow runs within the lookback window."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
        stmt = select(WorkflowRunORM).where(
            WorkflowRunORM.status.in_(_COMPLETED_STATUSES),
            WorkflowRunORM.completed_at >= cutoff,
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            WorkflowRunSummary(
                workflow_id=r.workflow_id,
                workflow_type=r.workflow_type,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in rows
        ]

    async def count_invocations_for_run(self, workflow_id: UUID) -> int:
        """Return the number of agent_invocation rows for a workflow_id."""
        stmt = select(func.count()).where(
            AgentInvocationORM.workflow_id == workflow_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()


class SqlRecommendationRepository(IRecommendationRepository):
    """SQLAlchemy implementation of IRecommendationRepository.

    Reads from recommendation_outcome (which carries action_signal, confidence,
    company_id, actual_t1d, actual_t1w). The ai_recommendation table (used by
    plan Mode B workflows) carries sample_size; we fall back to the
    recommendation_outcome table columns for the data available at MVP.

    NOTE: Until the full ai_recommendation table from PLAN-F-006/007/008/009/010
    is in place with sample_size, this implementation reads from
    recommendation_outcome. When those plans are executed, this repository
    should be updated to join ai_recommendation for sample_size, rationale etc.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_company(
        self,
        company_id: UUID,
        limit: int,
    ) -> list[RecommendationWithOutcome]:
        """Return recommendations for a company joined with outcome data."""
        stmt = (
            select(RecommendationOutcomeORM)
            .where(RecommendationOutcomeORM.company_id == company_id)
            .order_by(RecommendationOutcomeORM.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        return [
            RecommendationWithOutcome(
                rec_id=r.rec_id,
                company_ticker="",  # populated by caller from get_company_ticker
                action_signal=r.action_signal or "HOLD",
                confidence=r.confidence or 0.0,
                sample_size=0,  # recommendation_outcome has no sample_size at MVP
                generated_at=r.created_at,
                actual_t1d=r.actual_t1d,
                actual_t1w=r.actual_t1w,
                accuracy=None,
            )
            for r in rows
        ]

    async def get_company_ticker(self, company_id: UUID) -> str | None:
        """
        Return the ticker symbol for a company.

        At MVP, company ticker lives in the company / market tables.
        Returns None if not resolvable at this layer.
        """
        # At MVP there is no dedicated company table wired to this repo.
        # Return None; the service uses "" as fallback.
        return None
