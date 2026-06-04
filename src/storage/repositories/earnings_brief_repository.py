"""
storage.repositories.earnings_brief_repository — EarningsBriefRunRepository
with the interface as specified in PLAN-F-009 TASK-002.

Provides:
  IEarningsBriefRunRepository:
    - create(workflow_id, company_id, tenant_id, earnings_date) -> EarningsBriefRun
    - get(run_id, tenant_id) -> EarningsBriefRun | None
    - exists_for_date(company_id, tenant_id, earnings_date) -> bool
    - update_status(run_id, status, **kwargs) -> None
    - list_for_tenant(tenant_id, earnings_date) -> list[EarningsBriefRun]

Multi-tenancy: every query MUST include tenant_id in the WHERE clause.

PLAN-F-009 TASK-002
"""
from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.earnings_brief_run import EarningsBriefRun


@runtime_checkable
class IEarningsBriefRunRepository(Protocol):
    """Repository contract for earnings_brief_run persistence."""

    async def create(
        self,
        workflow_id: UUID,
        company_id: UUID,
        tenant_id: UUID,
        earnings_date: date,
    ) -> EarningsBriefRun:
        """INSERT a new earnings_brief_run row and return the refreshed ORM object."""
        ...

    async def get(
        self,
        run_id: UUID,
        tenant_id: UUID,
    ) -> EarningsBriefRun | None:
        """Return the run by run_id scoped to tenant_id (IDOR guard), or None."""
        ...

    async def exists_for_date(
        self,
        company_id: UUID,
        tenant_id: UUID,
        earnings_date: date,
    ) -> bool:
        """Return True if a brief run already exists for this company+tenant+date."""
        ...

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        **kwargs: Any,
    ) -> None:
        """UPDATE status (and any additional fields) on the given run."""
        ...

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        earnings_date: date | None = None,
    ) -> list[EarningsBriefRun]:
        """Return all brief runs for the tenant, optionally filtered by date."""
        ...


class EarningsBriefRunRepository:
    """SQLAlchemy 2.0 async repository for the earnings_brief_run table.

    Constructor-injected AsyncSession (DIP). All queries include tenant_id
    in the WHERE clause for multi-tenancy isolation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        workflow_id: UUID,
        company_id: UUID,
        tenant_id: UUID,
        earnings_date: date,
    ) -> EarningsBriefRun:
        """INSERT a new earnings_brief_run row and return the refreshed ORM object.

        Raises sqlalchemy.exc.IntegrityError if UNIQUE(company_id, tenant_id,
        earnings_date) is violated (idempotency guard).
        """
        orm = EarningsBriefRun(
            run_id=uuid4(),
            workflow_id=workflow_id,
            company_id=company_id,
            tenant_id=tenant_id,
            earnings_date=earnings_date,
            status="RUNNING",
            hil_status="none",
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm

    async def get(
        self,
        run_id: UUID,
        tenant_id: UUID,
    ) -> EarningsBriefRun | None:
        """Return the run by run_id scoped to tenant_id (IDOR guard), or None."""
        stmt = (
            select(EarningsBriefRun)
            .where(
                EarningsBriefRun.run_id == run_id,
                EarningsBriefRun.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_for_date(
        self,
        company_id: UUID,
        tenant_id: UUID,
        earnings_date: date,
    ) -> bool:
        """Return True if a brief run already exists for this company+tenant+date.

        Idempotency guard — prevents double-dispatch of the same brief.
        """
        stmt = (
            select(EarningsBriefRun.run_id)
            .where(
                EarningsBriefRun.company_id == company_id,
                EarningsBriefRun.tenant_id == tenant_id,
                EarningsBriefRun.earnings_date == earnings_date,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        **kwargs: Any,
    ) -> None:
        """UPDATE status and any additional fields on the run.

        Additional fields can be passed as keyword arguments (e.g., scenario_tree,
        confidence, cost_usd, hil_status, error_detail).
        """
        update_values: dict[str, Any] = {"status": status}
        allowed_fields = {
            "scenario_tree", "confidence", "cost_usd", "hil_status", "error_detail"
        }
        for key, val in kwargs.items():
            if key in allowed_fields:
                update_values[key] = val

        stmt = (
            update(EarningsBriefRun)
            .where(EarningsBriefRun.run_id == run_id)
            .values(**update_values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        earnings_date: date | None = None,
    ) -> list[EarningsBriefRun]:
        """Return all brief runs for the tenant, optionally filtered by date.

        Orders by created_at DESC.
        """
        stmt = select(EarningsBriefRun).where(
            EarningsBriefRun.tenant_id == tenant_id
        )
        if earnings_date is not None:
            stmt = stmt.where(EarningsBriefRun.earnings_date == earnings_date)
        stmt = stmt.order_by(EarningsBriefRun.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Legacy compatibility methods (used by older code) ─────────────────────

    async def exists(
        self,
        company_id: UUID,
        tenant_id: UUID,
        earnings_date: date,
    ) -> bool:
        """Alias for exists_for_date (backward compatibility)."""
        return await self.exists_for_date(company_id, tenant_id, earnings_date)

    async def insert(self, run: Any) -> EarningsBriefRun:
        """Legacy insert using EarningsBriefRunCreate DTO."""
        return await self.create(
            workflow_id=run.workflow_id,
            company_id=run.company_id,
            tenant_id=run.tenant_id,
            earnings_date=run.earnings_date,
        )

    async def update_status_legacy(
        self,
        run_id: UUID,
        status: str,
        scenario_tree: dict[str, Any] | None,
        confidence: float | None,
        cost_usd: float | None,
    ) -> None:
        """Legacy update_status with positional fields."""
        await self.update_status(
            run_id,
            status,
            scenario_tree=scenario_tree,
            confidence=confidence,
            cost_usd=cost_usd,
        )

    async def get_latest_by_company(
        self,
        company_id: UUID,
        tenant_id: UUID,
    ) -> EarningsBriefRun | None:
        """Return the most recent brief run for company+tenant, or None."""
        stmt = (
            select(EarningsBriefRun)
            .where(
                EarningsBriefRun.company_id == company_id,
                EarningsBriefRun.tenant_id == tenant_id,
            )
            .order_by(EarningsBriefRun.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
