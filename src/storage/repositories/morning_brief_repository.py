"""
storage.repositories.morning_brief_repository — IMorningBriefRepository.

Provides insert / get_latest_by_user / update_hil_status / update_sent_at
operations over the brief table, scoped to morning_brief rows.

Every query is tenant_id scoped to prevent IDOR cross-tenant data leakage
(REQ-N-006).

PLAN-F-006 TASK-002
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.brief import Brief


# ── Pydantic DTOs ─────────────────────────────────────────────────────────────


class MorningBriefCreate(BaseModel):
    """DTO for inserting a new morning brief row."""

    brief_id: UUID = Field(default_factory=uuid4)
    brief_type: str = "morning_brief"
    user_id: UUID
    tenant_id: UUID
    workflow_id: UUID
    content: str                  # HTML/text body of the brief
    confidence: float | None = None
    cost_usd: float | None = None


# ── Protocol interface ────────────────────────────────────────────────────────


@runtime_checkable
class IMorningBriefRepository(Protocol):
    """Repository contract for morning brief persistence.

    All methods are tenant-scoped for IDOR prevention (REQ-N-006).
    """

    async def insert(self, dto: MorningBriefCreate) -> Brief:
        """INSERT a new morning brief row and return the ORM object."""
        ...

    async def get_latest_by_user(
        self, user_id: UUID, tenant_id: UUID
    ) -> Brief | None:
        """Return the most recent morning brief for the given user+tenant, or None."""
        ...

    async def update_hil_status(
        self,
        brief_id: UUID,
        tenant_id: UUID,
        hil_status: str,
    ) -> None:
        """Update hil_status on the brief row."""
        ...

    async def update_sent_at(
        self,
        brief_id: UUID,
        tenant_id: UUID,
        sent_at: datetime,
    ) -> None:
        """Set sent_at on the brief row to record dispatch time."""
        ...

    async def list_by_user(
        self,
        user_id: UUID,
        tenant_id: UUID,
        brief_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Brief]:
        """Return a paginated list of briefs for the given user+tenant."""
        ...


# ── SQLAlchemy implementation ─────────────────────────────────────────────────


class MorningBriefRepository:
    """SQLAlchemy 2.0 async repository for morning brief rows.

    Constructor-injected AsyncSession (DIP). All queries include tenant_id
    in the WHERE clause as a mandatory tenant isolation guard (REQ-N-006).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, dto: MorningBriefCreate) -> Brief:
        """INSERT a new morning brief row and return the refreshed ORM row."""
        orm = Brief(
            brief_id=dto.brief_id,
            type=dto.brief_type,
            brief_type=dto.brief_type,
            user_id=dto.user_id,
            tenant_id=dto.tenant_id,
            workflow_id=dto.workflow_id,
            content={"body": dto.content},
            confidence=dto.confidence or 0.0,
            cost_usd=dto.cost_usd or 0.0,
            hil_status="none",
            sent_at=None,
            cost_limited=False,
            hil_reviewed=False,
            hil_approved=None,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm

    async def get_latest_by_user(
        self, user_id: UUID, tenant_id: UUID
    ) -> Brief | None:
        """Return the most recent morning brief for user+tenant, or None.

        Ordered by created_at DESC so the newest row is always returned.
        Tenant-scoped (REQ-N-006).
        """
        stmt = (
            select(Brief)
            .where(
                Brief.user_id == user_id,
                Brief.tenant_id == tenant_id,
                Brief.brief_type == "morning_brief",
            )
            .order_by(Brief.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_hil_status(
        self,
        brief_id: UUID,
        tenant_id: UUID,
        hil_status: str,
    ) -> None:
        """Update hil_status on a morning brief row.

        Tenant-scoped to prevent cross-tenant mutation (REQ-N-006).

        Args:
            brief_id: Primary key of the brief to update.
            tenant_id: Tenant the brief belongs to (IDOR guard).
            hil_status: New status value: 'none'|'pending'|'approved'|'rejected'.
        """
        stmt = (
            update(Brief)
            .where(
                Brief.brief_id == brief_id,
                Brief.tenant_id == tenant_id,
            )
            .values(hil_status=hil_status)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def update_sent_at(
        self,
        brief_id: UUID,
        tenant_id: UUID,
        sent_at: datetime,
    ) -> None:
        """Set sent_at on a morning brief row to record email dispatch time.

        Tenant-scoped (REQ-N-006).
        """
        stmt = (
            update(Brief)
            .where(
                Brief.brief_id == brief_id,
                Brief.tenant_id == tenant_id,
            )
            .values(sent_at=sent_at)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_by_user(
        self,
        user_id: UUID,
        tenant_id: UUID,
        brief_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Brief]:
        """Return a paginated list of briefs for the given user+tenant.

        Optionally filtered by brief_type. Ordered newest-first.
        Tenant-scoped (REQ-N-006).
        """
        filters = [
            Brief.user_id == user_id,
            Brief.tenant_id == tenant_id,
        ]
        if brief_type is not None:
            filters.append(Brief.brief_type == brief_type)

        stmt = (
            select(Brief)
            .where(*filters)
            .order_by(Brief.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
