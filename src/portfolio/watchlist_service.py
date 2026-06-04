"""
portfolio.watchlist_service — WatchlistService domain service.

Manages the user watchlist. All operations are idempotent where appropriate
and enforce tenant isolation by passing tenant_id to every repository call.
"""
from __future__ import annotations

import uuid

from src.storage.models.portfolio import WatchlistItem
from src.portfolio.interfaces import IWatchlistItemRepository


class WatchlistService:
    """Domain service for watchlist management.

    Dependencies are injected via the constructor (DIP).
    """

    def __init__(self, watchlist_repo: IWatchlistItemRepository) -> None:
        self._watchlist_repo = watchlist_repo

    async def add_to_watchlist(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        ticker: str,
    ) -> WatchlistItem:
        """Add a company to the user's watchlist (idempotent).

        If the company is already on the watchlist, the existing item is returned.
        """
        return await self._watchlist_repo.add(tenant_id, user_id, company_id, ticker)

    async def remove_from_watchlist(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        """Remove a company from the user's watchlist. No-op if not present."""
        await self._watchlist_repo.remove(tenant_id, user_id, company_id)

    async def list_watchlist(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[WatchlistItem]:
        """Return all watchlist items for the user. Returns empty list, not error."""
        return await self._watchlist_repo.list_by_user(tenant_id, user_id)
