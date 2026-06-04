"""
storage.repositories.infrastructure_cost_repo — IInfrastructureCostRepository
interface and PostgresInfrastructureCostRepository implementation.

All queries support an optional tenant_id for multi-tenancy readiness.
When tenant_id is None the query returns the global total (single-tenant MVP view).

Introduced by PLAN-N-005 TASK-002.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.infrastructure_cost import InfraCostCategory, InfrastructureCost


class IInfrastructureCostRepository(ABC):
    """Abstract interface for infrastructure_cost persistence operations."""

    @abstractmethod
    async def insert(self, record: InfrastructureCost) -> InfrastructureCost:
        """Persist a new InfrastructureCost record.

        Returns the persisted instance with cost_id populated.
        """

    @abstractmethod
    async def monthly_total(
        self,
        billing_month: date,
        tenant_id: uuid.UUID | None = None,
    ) -> float:
        """Return sum of cost_usd for the given billing_month.

        billing_month must be the first day of the month.
        Raises ValueError if billing_month.day != 1.
        Returns 0.0 when no rows exist.
        If tenant_id is None, returns the global total (single-tenant MVP).
        """

    @abstractmethod
    async def monthly_by_category(
        self,
        billing_month: date,
        tenant_id: uuid.UUID | None = None,
    ) -> list[tuple[InfraCostCategory, str, float]]:
        """Return [(category, description, cost_usd)] for the billing month.

        billing_month must be the first day of the month.
        Raises ValueError if billing_month.day != 1.
        Results are ordered by cost_usd DESC.
        Multiple rows with the same category are returned individually (not merged).
        Returns an empty list when no rows exist.
        If tenant_id is None, returns rows across all tenants.
        """


class PostgresInfrastructureCostRepository(IInfrastructureCostRepository):
    """SQLAlchemy 2.0 async implementation of IInfrastructureCostRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _validate_billing_month(self, billing_month: date) -> None:
        """Raise ValueError if billing_month is not the first day of a month."""
        if billing_month.day != 1:
            raise ValueError(
                f"billing_month must be the first day of a month; "
                f"got {billing_month.isoformat()}"
            )

    async def insert(self, record: InfrastructureCost) -> InfrastructureCost:
        """Persist the record and return it with cost_id populated."""
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def monthly_total(
        self,
        billing_month: date,
        tenant_id: uuid.UUID | None = None,
    ) -> float:
        """Return sum of cost_usd for the given billing_month.

        Uses EXTRACT(year) and EXTRACT(month) to match rows — the billing_month
        first-day normalisation is enforced by _validate_billing_month.
        """
        self._validate_billing_month(billing_month)

        stmt = select(
            func.coalesce(func.sum(InfrastructureCost.cost_usd), 0.0)
        ).where(
            func.extract("year", InfrastructureCost.billing_month)
            == billing_month.year,
            func.extract("month", InfrastructureCost.billing_month)
            == billing_month.month,
        )

        if tenant_id is not None:
            stmt = stmt.where(InfrastructureCost.tenant_id == tenant_id)

        result = await self._session.execute(stmt)
        return float(result.scalar_one())

    async def monthly_by_category(
        self,
        billing_month: date,
        tenant_id: uuid.UUID | None = None,
    ) -> list[tuple[InfraCostCategory, str, float]]:
        """Return (category, description, cost_usd) rows for the billing month.

        Results ordered by cost_usd DESC. Each row is returned individually —
        grouping by display category is the UI's responsibility.
        """
        self._validate_billing_month(billing_month)

        stmt = (
            select(
                InfrastructureCost.category,
                InfrastructureCost.description,
                InfrastructureCost.cost_usd,
            )
            .where(
                func.extract("year", InfrastructureCost.billing_month)
                == billing_month.year,
                func.extract("month", InfrastructureCost.billing_month)
                == billing_month.month,
            )
            .order_by(InfrastructureCost.cost_usd.desc())
        )

        if tenant_id is not None:
            stmt = stmt.where(InfrastructureCost.tenant_id == tenant_id)

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            (InfraCostCategory(row.category), row.description, float(row.cost_usd))
            for row in rows
        ]
