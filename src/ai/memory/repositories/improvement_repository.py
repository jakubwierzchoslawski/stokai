"""
ImprovementRepository — SQLAlchemy 2.0 async implementation of IImprovementRepository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.interfaces.i_improvement_repository import IImprovementRepository
from src.ai.memory.models.improvement_models import ImprovementProposal as ImprovementProposalORM
from src.ai.memory.schemas.feedback_schemas import (
    ImprovementProposal,
    ImprovementProposalCreate,
    ProposalStatus,
)


class ImprovementRepository(IImprovementRepository):
    """SQLAlchemy 2.0 async repository for improvement proposals."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_proposal(
        self, proposal: ImprovementProposalCreate
    ) -> ImprovementProposal:
        """INSERT a new proposal with status='pending'."""
        orm = ImprovementProposalORM(
            proposal_id=uuid4(),
            proposal_type=proposal.proposal_type,
            description=proposal.description,
            proposed_changes=proposal.proposed_changes,
            status=ProposalStatus.PENDING.value,
            reviewed_by=None,
            reviewed_at=None,
            created_at=datetime.now(tz=timezone.utc),
            source_feedback_ids=proposal.source_feedback_ids,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return ImprovementProposal.model_validate(orm)

    async def list_pending(self) -> list[ImprovementProposal]:
        """Return proposals with status='pending'."""
        stmt = select(ImprovementProposalORM).where(
            ImprovementProposalORM.status == ProposalStatus.PENDING.value
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [ImprovementProposal.model_validate(r) for r in rows]

    async def update_status(
        self,
        proposal_id: UUID,
        status: ProposalStatus,
        reviewed_by: UUID,
    ) -> ImprovementProposal:
        """Update status, reviewed_by, and reviewed_at."""
        stmt = (
            update(ImprovementProposalORM)
            .where(ImprovementProposalORM.proposal_id == proposal_id)
            .values(
                status=status.value,
                reviewed_by=reviewed_by,
                reviewed_at=datetime.now(tz=timezone.utc),
            )
            .returning(ImprovementProposalORM)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one()
        await self._session.flush()
        return ImprovementProposal.model_validate(orm)

    async def get_proposal(self, proposal_id: UUID) -> ImprovementProposal | None:
        """Return a proposal by ID or None."""
        result = await self._session.execute(
            select(ImprovementProposalORM).where(
                ImprovementProposalORM.proposal_id == proposal_id
            )
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return ImprovementProposal.model_validate(orm)
