"""
briefs.repositories.golden_dataset_repository — GoldenDatasetRepository.

Persists GoldenDatasetCandidate rows. Written on feedback_type='edit'.
Consumed by PLAN-F-029 Admin AI Audit Console.

PLAN-F-026 TASK-003
"""
from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.briefs.interfaces.i_golden_dataset_repository import IGoldenDatasetRepository
from src.briefs.models.brief_models import GoldenDatasetCandidate
from src.briefs.schemas.brief_schemas import GoldenDatasetCandidateCreate

logger = logging.getLogger(__name__)


class GoldenDatasetRepository(IGoldenDatasetRepository):
    """SQLAlchemy 2.0 async repository for golden_dataset_candidate.

    Constructor-injected AsyncSession (DIP).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_candidate(
        self, candidate: GoldenDatasetCandidateCreate
    ) -> GoldenDatasetCandidate:
        """INSERT a new golden_dataset_candidate row and return the ORM instance."""
        orm = GoldenDatasetCandidate(
            candidate_id=uuid4(),
            tenant_id=candidate.tenant_id,
            brief_id=candidate.brief_id,
            user_id=candidate.user_id,
            original_content=candidate.original_content,
            correction=candidate.correction,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm
