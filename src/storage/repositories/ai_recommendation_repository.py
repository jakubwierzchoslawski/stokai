"""
storage.repositories.ai_recommendation_repository — AiRecommendationRepository.

Provides save and list_for_company operations over the ai_recommendation table.
Every query is tenant-scoped to prevent IDOR data leakage.

PLAN-F-007 TASK-010
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.workflows.state import WorkflowState
from src.storage.models.ai_recommendation import AiRecommendation


class AiRecommendationRepository:
    """SQLAlchemy 2.0 async repository for the ai_recommendation table.

    Constructor-injected AsyncSession — no session creation inside methods (DIP).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, state: WorkflowState) -> UUID:
        """Persist a recommendation from a completed WorkflowState.

        Maps WorkflowState.recommendation → ai_recommendation row.
        For on-demand runs, event_id is NULL.

        Args:
            state: The final WorkflowState after workflow completion.

        Returns:
            The recommendation_id UUID of the newly created row.
        """
        orm = AiRecommendation(
            workflow_id=state.workflow_id,
            tenant_id=state.tenant_id,
            company_id=state.company_id,
            event_id=None,  # NULL for on-demand runs (event deep-dive sets this)
            workflow_type=state.workflow_type.value,
            recommendation=state.recommendation,
            overall_confidence=state.overall_confidence,
            status=state.status.value,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm.recommendation_id

    async def list_for_company(
        self,
        company_id: UUID,
        tenant_id: UUID,
        limit: int = 10,
    ) -> list[AiRecommendation]:
        """Return the most recent recommendations for a company, tenant-scoped.

        Args:
            company_id: UUID of the company.
            tenant_id: Tenant identifier for IDOR prevention.
            limit: Maximum number of rows to return (default 10).

        Returns:
            List of AiRecommendation ORM objects, newest first.
        """
        stmt = (
            select(AiRecommendation)
            .where(
                AiRecommendation.company_id == company_id,
                AiRecommendation.tenant_id == tenant_id,
            )
            .order_by(AiRecommendation.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
