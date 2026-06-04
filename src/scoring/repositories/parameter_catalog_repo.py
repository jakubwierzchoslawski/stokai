"""Parameter catalog repository.

Manages DSL parameter definitions — what named parameters are available for
use in indicator formulas.
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, String, Text, select, update
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# Default parameters seeded on startup
DEFAULT_PARAMETERS = [
    {"name": "revenue", "description": "Total revenue", "source_field": "financials.revenue"},
    {"name": "net_income", "description": "Net income", "source_field": "financials.net_income"},
    {"name": "pe_ratio", "description": "Price to earnings ratio", "source_field": "ratios.pe_ratio"},
    {"name": "roe", "description": "Return on equity", "source_field": "ratios.roe"},
    {"name": "debt_to_equity", "description": "Debt to equity ratio", "source_field": "ratios.debt_to_equity"},
    {"name": "price", "description": "Stock price", "source_field": "market.price"},
    {"name": "eps", "description": "Earnings per share", "source_field": "financials.eps"},
]


class _Base(DeclarativeBase):
    pass


class _DslParameterRow(_Base):
    __tablename__ = "dsl_parameter"

    parameter_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    source_field = Column(String(200), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)


class ParameterCatalogRepository:
    """Repository for DSL parameter catalog management."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, tenant_id: UUID) -> list[dict]:
        """List all parameters for a tenant (enabled and disabled)."""
        stmt = select(_DslParameterRow).where(
            _DslParameterRow.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        return [_row_to_dict(r) for r in result.scalars().all()]

    async def list_enabled(self, tenant_id: UUID) -> list[str]:
        """Return names of enabled parameters for a tenant."""
        stmt = select(_DslParameterRow.name).where(
            _DslParameterRow.tenant_id == tenant_id,
            _DslParameterRow.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.fetchall()]

    async def add(
        self,
        tenant_id: UUID,
        name: str,
        description: str | None = None,
        source_field: str | None = None,
    ) -> dict:
        """Add a new parameter to the catalog."""
        row = _DslParameterRow(
            parameter_id=uuid4(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            source_field=source_field,
            enabled=True,
            created_at=datetime.utcnow(),
        )
        self._session.add(row)
        await self._session.flush()
        return _row_to_dict(row)

    async def enable(self, name: str, tenant_id: UUID) -> bool:
        """Enable a parameter. Returns True if found and updated."""
        stmt = (
            update(_DslParameterRow)
            .where(
                _DslParameterRow.name == name,
                _DslParameterRow.tenant_id == tenant_id,
            )
            .values(enabled=True)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def disable(self, name: str, tenant_id: UUID) -> bool:
        """Disable a parameter. Returns True if found and updated."""
        stmt = (
            update(_DslParameterRow)
            .where(
                _DslParameterRow.name == name,
                _DslParameterRow.tenant_id == tenant_id,
            )
            .values(enabled=False)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def get_definition(self, name: str, tenant_id: UUID) -> dict | None:
        """Get a parameter definition by name."""
        stmt = select(_DslParameterRow).where(
            _DslParameterRow.name == name,
            _DslParameterRow.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _row_to_dict(row) if row else None

    async def seed_defaults(self, tenant_id: UUID) -> int:
        """Seed default parameters if catalog is empty for this tenant.

        Returns:
            Number of parameters seeded (0 if already populated).
        """
        existing = await self.list_enabled(tenant_id)
        if existing:
            logger.debug("Parameter catalog already populated for tenant %s — skipping seed.", tenant_id)
            return 0

        seeded = 0
        for param in DEFAULT_PARAMETERS:
            await self.add(
                tenant_id=tenant_id,
                name=param["name"],
                description=param["description"],
                source_field=param["source_field"],
            )
            seeded += 1
        logger.info("Seeded %d default parameters for tenant %s", seeded, tenant_id)
        return seeded


def _row_to_dict(row: _DslParameterRow) -> dict:
    return {
        "parameter_id": str(row.parameter_id),
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "description": row.description,
        "source_field": row.source_field,
        "enabled": row.enabled,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
