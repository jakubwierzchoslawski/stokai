"""
storage.repositories.market_source_binding_repo — IBindingRepository interface and
PostgresBindingRepository implementation.

Manages market-to-source bindings. upsert() uses PostgreSQL INSERT...ON CONFLICT
(composite PK) DO UPDATE to create-or-replace semantics in a single round-trip.

No business logic lives here — only data access.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.market_source_binding import MarketSourceBinding


class IBindingRepository(ABC):
    """Interface for market_source_binding persistence operations."""

    @abstractmethod
    async def list_for_market(self, market_id: uuid.UUID) -> list[MarketSourceBinding]:
        """Return all bindings for a given market (all interface types, all roles)."""

    @abstractmethod
    async def list_all(self) -> list[MarketSourceBinding]:
        """Return all bindings across all markets."""

    @abstractmethod
    async def upsert(
        self,
        market_id: uuid.UUID,
        interface_type: str,
        source_id: uuid.UUID,
        role: str,
    ) -> MarketSourceBinding:
        """Create or update a binding.

        On first call: inserts the row.
        On subsequent calls with the same (market_id, interface_type, source_id):
        updates the role column.

        Returns the persisted row.
        """

    @abstractmethod
    async def delete(
        self,
        market_id: uuid.UUID,
        interface_type: str,
        source_id: uuid.UUID,
    ) -> None:
        """Remove a specific binding. No-op if the row does not exist."""


class PostgresBindingRepository(IBindingRepository):
    """SQLAlchemy 2.0 async implementation of IBindingRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_market(self, market_id: uuid.UUID) -> list[MarketSourceBinding]:
        stmt = (
            select(MarketSourceBinding)
            .where(MarketSourceBinding.market_id == market_id)
            .order_by(MarketSourceBinding.interface_type, MarketSourceBinding.role)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[MarketSourceBinding]:
        stmt = select(MarketSourceBinding).order_by(
            MarketSourceBinding.market_id,
            MarketSourceBinding.interface_type,
            MarketSourceBinding.role,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        market_id: uuid.UUID,
        interface_type: str,
        source_id: uuid.UUID,
        role: str,
    ) -> MarketSourceBinding:
        """INSERT ... ON CONFLICT (composite PK) DO UPDATE SET role = :role."""
        stmt = (
            pg_insert(MarketSourceBinding)
            .values(
                market_id=str(market_id),
                interface_type=interface_type,
                source_id=str(source_id),
                role=role,
            )
            .on_conflict_do_update(
                index_elements=["market_id", "interface_type", "source_id"],
                set_={"role": role},
            )
            .returning(MarketSourceBinding)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        return row

    async def delete(
        self,
        market_id: uuid.UUID,
        interface_type: str,
        source_id: uuid.UUID,
    ) -> None:
        stmt = delete(MarketSourceBinding).where(
            MarketSourceBinding.market_id == market_id,
            MarketSourceBinding.interface_type == interface_type,
            MarketSourceBinding.source_id == source_id,
        )
        await self._session.execute(stmt)
