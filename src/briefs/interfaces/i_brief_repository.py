"""
briefs.interfaces.i_brief_repository — IBriefRepository abstract interface.

PLAN-F-026 TASK-001
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from src.briefs.schemas.brief_schemas import BriefProjection, BriefType


class IBriefRepository(ABC):
    """Abstract repository for briefs projected from workflow_run."""

    @abstractmethod
    async def list_briefs(
        self,
        tenant_id: UUID,
        brief_type: Optional[BriefType],
        cursor: Optional[str],
        limit: int,
    ) -> tuple[list[BriefProjection], Optional[str]]:
        """Return (items, next_cursor) sorted by completed_at DESC.

        cursor is a base64-encoded composite of completed_at + workflow_id.
        next_cursor is None when there are no further pages.
        """
        ...

    @abstractmethod
    async def get_brief(
        self,
        brief_id: UUID,
        tenant_id: UUID,
    ) -> Optional[BriefProjection]:
        """Return the brief or None.

        Returns None for both missing records and tenant_id mismatches
        (IDOR prevention — never expose whether a record exists).
        """
        ...
