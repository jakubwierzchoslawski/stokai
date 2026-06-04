"""
storage.position_repository — PositionRepository.

All queries are tenant-scoped by joining through portfolio to verify ownership.
Inherits TenantScopedRepository for structural tenant isolation enforcement.
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.portfolio import Portfolio, Position
from src.storage.repositories.base import TenantScopedRepository


class PositionRepository(TenantScopedRepository):
    """SQLAlchemy 2.0 async repository for the position table.

    Tenant isolation is enforced by joining position → portfolio and filtering
    on portfolio.tenant_id. The position table has no tenant_id column; ownership
    is verified through the parent portfolio.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _scoped_position_select(self, tenant_id: uuid.UUID):
        """Return a SELECT(Position) joined to portfolio filtered by tenant_id."""
        self._guard_tenant_id(tenant_id)
        return (
            select(Position)
            .join(Portfolio, Position.portfolio_id == Portfolio.portfolio_id)
            .where(Portfolio.tenant_id == tenant_id)
        )

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
        """Insert a single position row and return the persisted entity."""
        position = Position(
            position_id=uuid.uuid4(),
            portfolio_id=portfolio_id,
            company_id=company_id,
            ticker=ticker,
            shares=shares,
            cost_basis=cost_basis,
            source=source,
        )
        self._session.add(position)
        await self._session.flush()
        await self._session.refresh(position)
        return position

    async def list_by_portfolio(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
    ) -> list[Position]:
        """Return all positions for a portfolio, verifying tenant_id ownership."""
        stmt = self._scoped_position_select(tenant_id).where(
            Position.portfolio_id == portfolio_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self,
        tenant_id: uuid.UUID,
        position_id: uuid.UUID,
    ) -> Position | None:
        """Return a position by PK, verifying tenant ownership via portfolio join."""
        stmt = self._scoped_position_select(tenant_id).where(
            Position.position_id == position_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(
        self,
        tenant_id: uuid.UUID,
        position_id: uuid.UUID,
    ) -> None:
        """Delete a position by PK (verifies tenant ownership first)."""
        position = await self.get(tenant_id, position_id)
        if position is not None:
            await self._session.delete(position)
            await self._session.flush()

    async def bulk_create(
        self,
        tenant_id: uuid.UUID,
        portfolio_id: uuid.UUID,
        rows: list[dict],
    ) -> list[Position]:
        """Insert multiple positions in a single flush.

        Each entry in ``rows`` must have keys: company_id, ticker, shares, source,
        and optionally cost_basis.

        Returns the list of persisted Position objects.
        """
        self._guard_tenant_id(tenant_id)
        positions = [
            Position(
                position_id=uuid.uuid4(),
                portfolio_id=portfolio_id,
                company_id=row["company_id"],
                ticker=row["ticker"],
                shares=row["shares"],
                cost_basis=row.get("cost_basis"),
                source=row.get("source", "csv"),
            )
            for row in rows
        ]
        self._session.add_all(positions)
        await self._session.flush()
        for p in positions:
            await self._session.refresh(p)
        return positions
