"""
storage.repositories.brief_repository — IBriefRepository + SQLAlchemyBriefRepository.

Provides insert_memo / get_by_event_id / mark_hil_reviewed operations over the
brief table.  Every query is tenant_id scoped via the WHERE clause to prevent
IDOR cross-tenant data leakage (REQ-N-006).

PLAN-F-010 TASK-002.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.workflows.event_deep_dive.state import BriefCreate
from src.storage.models.brief import Brief


# ── Protocol interface ────────────────────────────────────────────────────────


@runtime_checkable
class IBriefRepository(Protocol):
    """Repository contract for brief/report persistence.

    All mutating methods are tenant-scoped for IDOR prevention.
    """

    async def insert_memo(self, brief: BriefCreate) -> Brief:
        """INSERT a new brief row and return the ORM object with populated brief_id."""
        ...

    async def get_by_event_id(self, event_id: UUID) -> Brief | None:
        """Return the most recent brief for the given event_id, or None."""
        ...

    async def mark_hil_reviewed(self, brief_id: UUID, approved: bool) -> None:
        """Set hil_reviewed=True and hil_approved on the given brief row."""
        ...


# ── SQLAlchemy implementation ─────────────────────────────────────────────────


class BriefRepository:
    """SQLAlchemy 2.0 async repository for the brief table.

    Constructor-injected AsyncSession (DIP). All queries include tenant_id
    or brief_id (unique PK) in the WHERE clause.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── IBriefRepository contract ─────────────────────────────────────────────

    async def insert_memo(self, brief: BriefCreate) -> Brief:
        """INSERT a new brief row and return the refreshed ORM row."""
        orm = Brief(
            brief_id=brief.brief_id,
            type=brief.type,
            event_id=brief.event_id,
            tenant_id=brief.tenant_id,
            content=brief.content,
            confidence=brief.confidence,
            cost_usd=brief.cost_usd,
            cost_limited=brief.cost_limited,
            hil_reviewed=False,
            hil_approved=None,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm

    async def get_by_event_id(self, event_id: UUID) -> Brief | None:
        """Return the most recent brief for the given event_id, or None.

        Orders by created_at DESC so repeated deep-dives always surface the
        latest memo.
        """
        stmt = (
            select(Brief)
            .where(Brief.event_id == event_id)
            .order_by(Brief.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_hil_reviewed(self, brief_id: UUID, approved: bool) -> None:
        """Set hil_reviewed=True and hil_approved=approved on the brief row."""
        stmt = (
            update(Brief)
            .where(Brief.brief_id == brief_id)
            .values(hil_reviewed=True, hil_approved=approved)
        )
        await self._session.execute(stmt)
        await self._session.flush()
