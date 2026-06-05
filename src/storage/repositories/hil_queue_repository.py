"""
storage.repositories.hil_queue_repository — HILQueueRepository.

Provides CRUD operations over the hil_queue_item table. Every query is
scoped by tenant_id to prevent cross-tenant IDOR leakage (REQ-N-006).

No business logic lives here — only parameterised queries.

PLAN-F-013 TASK-002
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import DateTime, select, update
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import sqlalchemy as sa

# SQLAlchemy >=2.0.36 removed TIMESTAMPTZ from dialects.postgresql
try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = DateTime(timezone=True)  # type: ignore[misc,assignment]


# ── Enum ──────────────────────────────────────────────────────────────────────

class HILStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED_APPROVED = "edited_approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


# ── ORM model ─────────────────────────────────────────────────────────────────

class HILQueueBase(DeclarativeBase):
    """Declarative base for HIL queue ORM model."""


class HILQueueItem(HILQueueBase):
    """ORM model for the hil_queue_item table.

    Multi-tenancy: every query MUST include tenant_id (REQ-N-006).
    """

    __tablename__ = "hil_queue_item"

    item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workflow_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    workflow_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    confidence: Mapped[float] = mapped_column(sa.Float, nullable=False)
    scheduled_send_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default=sa.text("'pending'")
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    lc_checkpoint_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMPTZ, nullable=True, server_default=sa.text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"HILQueueItem(item_id={self.item_id!r}, "
            f"status={self.status!r}, tenant_id={self.tenant_id!r})"
        )


# ── Pydantic DTOs ─────────────────────────────────────────────────────────────

class HILQueueItemCreate(BaseModel):
    """DTO for creating a new HIL queue item."""

    workflow_run_id: UUID
    workflow_type: str
    user_id: UUID
    tenant_id: UUID
    confidence: float
    scheduled_send_at: datetime
    lc_checkpoint_id: str


# ── Repository ────────────────────────────────────────────────────────────────

class HILQueueRepository:
    """SQLAlchemy 2.0 async repository for the hil_queue_item table.

    Constructor-injected AsyncSession (DIP). All queries include tenant_id
    in the WHERE clause as a mandatory tenant isolation guard (REQ-N-006).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, item: HILQueueItemCreate) -> HILQueueItem:
        """INSERT a new hil_queue_item row and return the ORM row.

        Status defaults to 'pending' at the database level.
        """
        orm = HILQueueItem(
            workflow_run_id=item.workflow_run_id,
            workflow_type=item.workflow_type,
            user_id=item.user_id,
            tenant_id=item.tenant_id,
            confidence=item.confidence,
            scheduled_send_at=item.scheduled_send_at,
            lc_checkpoint_id=item.lc_checkpoint_id,
            status=HILStatus.PENDING.value,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm

    async def list_pending(self, tenant_id: UUID) -> list[HILQueueItem]:
        """Return all pending items for a tenant, ordered by scheduled_send_at asc.

        Only returns rows with status='pending'. Tenant-scoped (REQ-N-006).
        """
        stmt = (
            select(HILQueueItem)
            .where(
                HILQueueItem.tenant_id == tenant_id,
                HILQueueItem.status == HILStatus.PENDING.value,
            )
            .order_by(HILQueueItem.scheduled_send_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, item_id: UUID, tenant_id: UUID) -> HILQueueItem | None:
        """Return a single HIL queue item scoped to tenant_id, or None.

        Returns None if item_id is valid but belongs to a different tenant —
        this prevents IDOR; callers should raise 404, not 403.
        """
        stmt = select(HILQueueItem).where(
            HILQueueItem.item_id == item_id,
            HILQueueItem.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        item_id: UUID,
        tenant_id: UUID,
        status: HILStatus,
        reviewer_id: UUID | None = None,
        reviewed_at: datetime | None = None,
    ) -> HILQueueItem:
        """Update the status (and optionally reviewer / reviewed_at) of a queue item.

        Returns the refreshed ORM row. Tenant-scoped (REQ-N-006).

        Raises:
            ValueError: If the item is not found after the update (should not
                happen in normal operation — indicates a race or wrong tenant_id).
        """
        values: dict = {"status": status.value}
        if reviewer_id is not None:
            values["reviewer_id"] = reviewer_id
        if reviewed_at is not None:
            values["reviewed_at"] = reviewed_at

        stmt = (
            update(HILQueueItem)
            .where(
                HILQueueItem.item_id == item_id,
                HILQueueItem.tenant_id == tenant_id,
            )
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

        # Re-fetch the updated row
        select_stmt = select(HILQueueItem).where(
            HILQueueItem.item_id == item_id,
            HILQueueItem.tenant_id == tenant_id,
        )
        result = await self._session.execute(select_stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(
                f"HIL queue item {item_id} not found after status update "
                f"(tenant_id={tenant_id})"
            )
        return row

    async def list_timed_out_pending(self, now: datetime) -> list[HILQueueItem]:
        """Return all pending items whose scheduled_send_at is in the past.

        Used by the Celery beat timeout task (TASK-006) to find items that
        have missed their deadline without reviewer action.

        Note: NOT tenant-scoped intentionally — the timeout task is a system
        operation that must sweep all tenants.
        """
        stmt = (
            select(HILQueueItem)
            .where(
                HILQueueItem.status == HILStatus.PENDING.value,
                HILQueueItem.scheduled_send_at < now,
            )
            .order_by(HILQueueItem.scheduled_send_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
