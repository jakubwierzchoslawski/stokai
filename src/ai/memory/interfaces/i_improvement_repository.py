"""
IImprovementRepository — abstract interface for improvement proposals.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.ai.memory.schemas.feedback_schemas import (
    ImprovementProposal,
    ImprovementProposalCreate,
    ProposalStatus,
)


class IImprovementRepository(ABC):
    """Abstract repository for improvement proposals."""

    @abstractmethod
    async def create_proposal(
        self, proposal: ImprovementProposalCreate
    ) -> ImprovementProposal:
        """INSERT a new improvement_proposal with status='pending'."""
        ...

    @abstractmethod
    async def list_pending(self) -> list[ImprovementProposal]:
        """Return all proposals with status='pending'."""
        ...

    @abstractmethod
    async def update_status(
        self,
        proposal_id: UUID,
        status: ProposalStatus,
        reviewed_by: UUID,
    ) -> ImprovementProposal:
        """Set status, reviewed_by, reviewed_at on a proposal."""
        ...

    @abstractmethod
    async def get_proposal(self, proposal_id: UUID) -> ImprovementProposal | None:
        """Return a single proposal by ID or None."""
        ...
