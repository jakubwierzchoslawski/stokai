"""
storage.watchlist_item_repository — WatchlistItemRepository.

All queries include tenant_id in the WHERE clause. Inherits TenantScopedRepository
for structural tenant isolation enforcement (REQ-N-006).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.portfolio import WatchlistItem
from src.storage.repositories.base import TenantScopedRepository


class WatchlistItemRepository(TenantScopedRepository):
    """SQLAlchemy 2.0 async repository for the watchlist_item table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        ticker: str,
    ) -> WatchlistItem:
        """Insert a watchlist item row and return the persisted entity.

        If the (tenant_id, user_id, company_id) combination already exists,
        the existing row is returned (idempotent).
        """
        existing = await self._find(tenant_id, user_id, company_id)
        if existing is not None:
            return existing

        item = WatchlistItem(
            item_id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=company_id,
            ticker=ticker,
        )
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def list_by_user(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[WatchlistItem]:
        """Return all watchlist items for a user within a tenant."""
        stmt = self._scoped_select(WatchlistItem, tenant_id).where(
            WatchlistItem.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def remove(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Delete a watchlist item; no-op if it does not exist."""
        item = await self._find(tenant_id, user_id, company_id)
        if item is not None:
            await self._session.delete(item)
            await self._session.flush()

    async def exists(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> bool:
        """Return True if the watchlist item exists for this tenant/user/company."""
        return (await self._find(tenant_id, user_id, company_id)) is not None

    async def _find(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> WatchlistItem | None:
        self._guard_tenant_id(tenant_id)
        stmt = (
            select(WatchlistItem)
            .where(
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.user_id == user_id,
                WatchlistItem.company_id == company_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
