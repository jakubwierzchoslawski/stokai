"""
storage.repositories.cost_record_repo — ICostRecordRepository interface and
PostgresCostRecordRepository implementation.

All queries are tenant-scoped to prevent IDOR leakage.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import date

from sqlalchemy import Date, Float, String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.cost_record import CostRecord


class ICostRecordRepository(ABC):
    """Interface for cost_record persistence operations."""

    @abstractmethod
    async def aggregate_monthly(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> float:
        """Return total cost_usd for the tenant in the given year/month.

        Returns 0.0 when no records exist.
        """

    @abstractmethod
    async def breakdown_by_source(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> list[dict]:
        """Return [{source, total_cost_usd}] grouped by source for the month."""

    @abstractmethod
    async def breakdown_by_model(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> list[dict]:
        """Return [{model, total_cost_usd}] grouped by model for the month."""

    @abstractmethod
    async def breakdown_by_workflow(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> list[dict]:
        """Return [{workflow_type, total_cost_usd}] grouped by workflow_type for the month."""

    @abstractmethod
    async def daily_totals(
        self, tenant_id: uuid.UUID, start: date, end: date
    ) -> list[dict]:
        """Return [{date, total_cost_usd}] one row per day in [start, end] inclusive."""

    @abstractmethod
    async def insert(self, record: CostRecord) -> CostRecord:
        """Persist a new CostRecord and return it with generated record_id."""

    @abstractmethod
    async def daily_total_for_user(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        target_date: date,
    ) -> float:
        """Return total cost_usd for a specific user on a specific date.

        Sums cost_record.cost_usd where user_id = :user_id AND
        tenant_id = :tenant_id AND date = :target_date.
        Returns 0.0 when no records exist.
        """

    @abstractmethod
    async def insert_for_workflow_run(
        self,
        workflow_run_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workflow_type: str,
        cost_usd: float,
        target_date: date,
    ) -> CostRecord:
        """Insert a cost_record row after a workflow run completes or is terminated.

        Used by base_workflow.py finally block to record telemetry for every run
        regardless of outcome (normal completion, WorkflowBudgetExceededError,
        or other exception).

        Args:
            workflow_run_id: UUID of the workflow_run row.
            user_id: UUID of the user who triggered the workflow.
            tenant_id: UUID of the tenant (multi-tenancy scope).
            workflow_type: Workflow type string (e.g. "morning_brief").
            cost_usd: Accumulated cost in USD at time of insert.
            target_date: Calendar date for cost aggregation (typically date.today()).

        Returns:
            Persisted CostRecord with generated record_id.
        """


class PostgresCostRecordRepository(ICostRecordRepository):
    """SQLAlchemy 2.0 async implementation of ICostRecordRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def aggregate_monthly(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> float:
        stmt = select(func.coalesce(func.sum(CostRecord.cost_usd), 0.0)).where(
            CostRecord.tenant_id == tenant_id,
            func.extract("year", CostRecord.date) == year,
            func.extract("month", CostRecord.date) == month,
        )
        result = await self._session.execute(stmt)
        return float(result.scalar_one())

    async def breakdown_by_source(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> list[dict]:
        stmt = (
            select(
                CostRecord.source,
                func.sum(CostRecord.cost_usd).label("total_cost_usd"),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                func.extract("year", CostRecord.date) == year,
                func.extract("month", CostRecord.date) == month,
            )
            .group_by(CostRecord.source)
            .order_by(func.sum(CostRecord.cost_usd).desc())
        )
        result = await self._session.execute(stmt)
        return [
            {"source": row.source, "total_cost_usd": float(row.total_cost_usd)}
            for row in result.all()
        ]

    async def breakdown_by_model(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> list[dict]:
        stmt = (
            select(
                CostRecord.model,
                func.sum(CostRecord.cost_usd).label("total_cost_usd"),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                func.extract("year", CostRecord.date) == year,
                func.extract("month", CostRecord.date) == month,
                CostRecord.model.isnot(None),
            )
            .group_by(CostRecord.model)
            .order_by(func.sum(CostRecord.cost_usd).desc())
        )
        result = await self._session.execute(stmt)
        return [
            {"model": row.model, "total_cost_usd": float(row.total_cost_usd)}
            for row in result.all()
        ]

    async def breakdown_by_workflow(
        self, tenant_id: uuid.UUID, year: int, month: int
    ) -> list[dict]:
        stmt = (
            select(
                CostRecord.workflow_type,
                func.sum(CostRecord.cost_usd).label("total_cost_usd"),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                func.extract("year", CostRecord.date) == year,
                func.extract("month", CostRecord.date) == month,
                CostRecord.workflow_type.isnot(None),
            )
            .group_by(CostRecord.workflow_type)
            .order_by(func.sum(CostRecord.cost_usd).desc())
        )
        result = await self._session.execute(stmt)
        return [
            {
                "workflow_type": row.workflow_type,
                "total_cost_usd": float(row.total_cost_usd),
            }
            for row in result.all()
        ]

    async def daily_totals(
        self, tenant_id: uuid.UUID, start: date, end: date
    ) -> list[dict]:
        stmt = (
            select(
                CostRecord.date,
                func.sum(CostRecord.cost_usd).label("total_cost_usd"),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.date >= start,
                CostRecord.date <= end,
            )
            .group_by(CostRecord.date)
            .order_by(CostRecord.date)
        )
        result = await self._session.execute(stmt)
        return [
            {"date": row.date.isoformat(), "total_cost_usd": float(row.total_cost_usd)}
            for row in result.all()
        ]

    async def insert(self, record: CostRecord) -> CostRecord:
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record

    async def daily_total_for_user(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        target_date: date,
    ) -> float:
        """Return total cost_usd for a specific user on a specific date.

        Returns 0.0 via COALESCE when no records exist.
        """
        stmt = select(func.coalesce(func.sum(CostRecord.cost_usd), 0.0)).where(
            CostRecord.user_id == user_id,
            CostRecord.tenant_id == tenant_id,
            CostRecord.date == target_date,
        )
        result = await self._session.execute(stmt)
        return float(result.scalar_one())

    async def insert_for_workflow_run(
        self,
        workflow_run_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workflow_type: str,
        cost_usd: float,
        target_date: date,
    ) -> CostRecord:
        """Insert a cost_record row after a workflow run completes or is terminated."""
        record = CostRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            workflow_run_id=workflow_run_id,
            date=target_date,
            source="workflow",
            workflow_type=workflow_type,
            cost_usd=cost_usd,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record
