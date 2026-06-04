"""
briefs.services.brief_service — BriefService.

Delegates to IBriefRepository. Maps projections to list/detail DTOs.
Enforces ownership check via repository's tenant_id guard.

PLAN-F-026 TASK-002
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from src.briefs.interfaces.i_brief_repository import IBriefRepository
from src.briefs.interfaces.i_brief_service import IBriefService
from src.briefs.schemas.brief_schemas import (
    BriefFeedbackCreate,
    BriefListResult,
    BriefProjection,
    BriefType,
)

logger = logging.getLogger(__name__)


class BriefNotFoundError(Exception):
    """Raised when a brief cannot be found or tenant_id does not match."""


class BriefService(IBriefService):
    """Concrete service for brief list / detail retrieval.

    Constructor-injected IBriefRepository (DIP).
    """

    def __init__(self, brief_repository: IBriefRepository) -> None:
        self._repo = brief_repository

    async def list_briefs(
        self,
        user_id: UUID,
        tenant_id: UUID,
        brief_type: Optional[BriefType],
        cursor: Optional[str],
        limit: int,
    ) -> BriefListResult:
        items, next_cursor = await self._repo.list_briefs(
            tenant_id=tenant_id,
            brief_type=brief_type,
            cursor=cursor,
            limit=limit,
        )
        return BriefListResult(items=items, next_cursor=next_cursor)

    async def get_brief_detail(
        self,
        brief_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
    ) -> BriefProjection:
        projection = await self._repo.get_brief(brief_id=brief_id, tenant_id=tenant_id)
        if projection is None:
            raise BriefNotFoundError(f"Brief {brief_id} not found for tenant {tenant_id}")
        return projection

    async def submit_feedback(
        self,
        brief_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        payload: BriefFeedbackCreate,
    ) -> None:
        """Not implemented in this service — delegated to BriefFeedbackService."""
        raise NotImplementedError("Use BriefFeedbackService.submit_feedback")
