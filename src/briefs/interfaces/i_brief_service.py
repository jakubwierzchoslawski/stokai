"""
briefs.interfaces.i_brief_service — IBriefService abstract interface.

PLAN-F-026 TASK-002
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from src.briefs.schemas.brief_schemas import (
    BriefFeedbackCreate,
    BriefListResult,
    BriefProjection,
    BriefType,
)


class IBriefService(ABC):
    """Abstract service for brief list, detail retrieval, and feedback submission."""

    @abstractmethod
    async def list_briefs(
        self,
        user_id: UUID,
        tenant_id: UUID,
        brief_type: Optional[BriefType],
        cursor: Optional[str],
        limit: int,
    ) -> BriefListResult:
        """Return paginated list of briefs for the tenant."""
        ...

    @abstractmethod
    async def get_brief_detail(
        self,
        brief_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
    ) -> BriefProjection:
        """Return full brief detail.

        Raises BriefNotFoundError when the brief does not exist or tenant_id
        does not match (IDOR prevention).
        """
        ...

    @abstractmethod
    async def submit_feedback(
        self,
        brief_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        payload: BriefFeedbackCreate,
    ) -> None:
        """Persist user feedback and, for edit type, a GoldenDatasetCandidate."""
        ...
