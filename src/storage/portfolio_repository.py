"""
storage.portfolio_repository — PortfolioRepository.

All queries are tenant-scoped. Inherits TenantScopedRepository for structural
tenant isolation enforcement on every query.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.portfolio import Portfolio
from src.storage.repositories.base import TenantScopedRepository


class PortfolioRepository(TenantScopedRepository):
    """SQLAlchemy 2.0 async repository for the portfolio table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
    ) -> Portfolio:
        """Insert a new portfolio row and return the persisted entity."""
        portfolio = Portfolio(
            portfolio_id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
        )
        self._session.add(portfolio)
        await self._session.flush()
        await self._session.refresh(portfolio)
        return portfolio

    async def list_by_user(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Portfolio]:
        """Return all portfolios for a user within a tenant."""
        stmt = self._scoped_select(Portfolio, tenant_id).where(
            Portfolio.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
    ) -> Portfolio | None:
        """Return a portfolio by PK scoped to tenant_id, or None."""
        stmt = self._scoped_select(Portfolio, tenant_id).where(
            Portfolio.portfolio_id == portfolio_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
    ) -> None:
        """Delete a portfolio by PK (positions cascade via DB FK)."""
        portfolio = await self.get(tenant_id, portfolio_id)
        if portfolio is not None:
            await self._session.delete(portfolio)
            await self._session.flush()
