"""
portfolio.interfaces — Protocol definitions for repository and lookup dependencies.

All protocols follow the Dependency Inversion Principle; concrete implementations
are injected by the composition root (FastAPI dependency injection layer).
"""
from __future__ import annotations

import uuid
from typing import Protocol

from src.storage.models.portfolio import Portfolio, Position, WatchlistItem


class IPortfolioRepository(Protocol):
    """Protocol for portfolio persistence operations."""

    async def create(self, tenant_id: uuid.UUID, user_id: uuid.UUID, name: str) -> Portfolio:
        ...

    async def list_by_user(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[Portfolio]:
        ...

    async def get(self, tenant_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio | None:
        ...

    async def delete(self, tenant_id: uuid.UUID, portfolio_id: uuid.UUID) -> None:
        ...


class IPositionRepository(Protocol):
    """Protocol for position persistence operations."""

    async def create(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        company_id: uuid.UUID,
        ticker: str,
        shares: float,
        source: str,
        cost_basis: float | None = None,
    ) -> Position:
        ...

    async def list_by_portfolio(
        self, tenant_id: uuid.UUID, portfolio_id: uuid.UUID
    ) -> list[Position]:
        ...

    async def get(self, tenant_id: uuid.UUID, position_id: uuid.UUID) -> Position | None:
        ...

    async def delete(self, tenant_id: uuid.UUID, position_id: uuid.UUID) -> None:
        ...

    async def bulk_create(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        rows: list[dict],
    ) -> list[Position]:
        ...


class IWatchlistItemRepository(Protocol):
    """Protocol for watchlist item persistence operations."""

    async def add(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        company_id: uuid.UUID,
        ticker: str,
    ) -> WatchlistItem:
        ...

    async def list_by_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[WatchlistItem]:
        ...

    async def remove(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID
    ) -> None:
        ...

    async def exists(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID
    ) -> bool:
        ...


class ICompanyLookup(Protocol):
    """Protocol for resolving a ticker symbol to a company_id."""

    async def resolve_ticker(self, ticker: str) -> uuid.UUID | None:
        """Return the company_id for the given ticker, or None if not found."""
        ...
