"""
storage.repositories.earnings_repositories — EarningsEventRepository and
EarningsBriefRunRepository (legacy — see earnings_brief_repository.py for the
canonical PLAN-F-009 TASK-002 interface).

Provides:
  IEarningsEventRepository:
    - get_upcoming(tenant_id, hours_ahead=24) -> list[EarningsEvent]
    - insert(event: EarningsEventCreate, tenant_id) -> EarningsEvent

  IEarningsBriefRunRepository:
    - exists(company_id, tenant_id, earnings_date) -> bool
    - insert(run: EarningsBriefRunCreate) -> EarningsBriefRun
    - update_status(run_id, status, scenario_tree, confidence, cost_usd) -> None
    - get_latest_by_company(company_id, tenant_id) -> EarningsBriefRun | None

Multi-tenancy: every query MUST include tenant_id in the WHERE clause to
prevent IDOR cross-tenant data leakage (REQ-N-006).

PLAN-F-009 TASK-002
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.earnings_brief_run import EarningsBriefRun
from src.storage.models.earnings_event import EarningsEvent


# ── DTOs ──────────────────────────────────────────────────────────────────────


class EarningsEventCreate(BaseModel):
    """Data required to insert a new earnings_event row."""

    company_id: UUID
    tenant_id: UUID
    earnings_date: date
    fiscal_quarter: str | None = None
    expected_eps: float | None = None


class EarningsBriefRunCreate(BaseModel):
    """Data required to insert a new earnings_brief_run row."""

    workflow_id: UUID
    company_id: UUID
    tenant_id: UUID
    earnings_date: date
    status: str = "running"
    hil_status: str = "none"


# ── Protocol interfaces ────────────────────────────────────────────────────────


@runtime_checkable
class IEarningsEventRepository(Protocol):
    """Repository contract for earnings_event persistence."""

    async def get_upcoming(
        self,
        tenant_id: UUID,
        hours_ahead: int = 24,
    ) -> list[EarningsEvent]:
        """Return all earnings events within the next hours_ahead hours."""
        ...

    async def insert(
        self,
        event: EarningsEventCreate,
        tenant_id: UUID,
    ) -> EarningsEvent:
        """INSERT a new earnings_event row and return the refreshed ORM object."""
        ...


@runtime_checkable
class IEarningsBriefRunRepository(Protocol):
    """Repository contract for earnings_brief_run persistence."""

    async def exists(
        self,
        company_id: UUID,
        tenant_id: UUID,
        earnings_date: date,
    ) -> bool:
        """Return True if a brief run already exists for this company+tenant+date."""
        ...

    async def insert(self, run: EarningsBriefRunCreate) -> EarningsBriefRun:
        """INSERT a new earnings_brief_run row and return the refreshed ORM object."""
        ...

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        scenario_tree: dict[str, Any] | None,
        confidence: float | None,
        cost_usd: float | None,
    ) -> None:
        """UPDATE status, scenario_tree, confidence, and cost_usd on the given run."""
        ...

    async def get_latest_by_company(
        self,
        company_id: UUID,
        tenant_id: UUID,
    ) -> EarningsBriefRun | None:
        """Return the most recent brief run for company+tenant, or None."""
        ...


# ── SQLAlchemy implementations ────────────────────────────────────────────────


class EarningsEventRepository:
    """SQLAlchemy 2.0 async repository for the earnings_event table.

    Constructor-injected AsyncSession (DIP). All queries include tenant_id
    in the WHERE clause for multi-tenancy isolation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_upcoming(
        self,
        tenant_id: UUID,
        hours_ahead: int = 24,
    ) -> list[EarningsEvent]:
        """Return earnings events for tenant within the next hours_ahead hours.

        The window is: now() <= earnings_date <= now() + hours_ahead.
        earnings_date is cast to date for comparison; DB stores DATE type.
        """
        now = datetime.now(tz=timezone.utc)
        window_end = now + timedelta(hours=hours_ahead)
        today = now.date()
        end_date = window_end.date()

        stmt = (
            select(EarningsEvent)
            .where(
                EarningsEvent.tenant_id == tenant_id,
                EarningsEvent.earnings_date >= today,
                EarningsEvent.earnings_date <= end_date,
            )
            .order_by(EarningsEvent.earnings_date)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()  # type: ignore[return-value]

    async def insert(
        self,
        event: EarningsEventCreate,
        tenant_id: UUID,
    ) -> EarningsEvent:
        """INSERT a new earnings_event row and return the refreshed ORM object."""
        orm = EarningsEvent(
            earnings_event_id=uuid4(),
            company_id=event.company_id,
            tenant_id=tenant_id,
            earnings_date=event.earnings_date,
            fiscal_quarter=event.fiscal_quarter,
            expected_eps=event.expected_eps,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm


class EarningsBriefRunRepository:
    """SQLAlchemy 2.0 async repository for the earnings_brief_run table.

    Constructor-injected AsyncSession (DIP). All queries include tenant_id
    or run_id (unique PK) in the WHERE clause.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(
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

    async def insert(self, run: EarningsBriefRunCreate) -> EarningsBriefRun:
        """INSERT a new earnings_brief_run row and return the refreshed ORM object.

        Raises sqlalchemy.exc.IntegrityError if UNIQUE(company_id, tenant_id,
        earnings_date) is violated (idempotency guard).
        """
        orm = EarningsBriefRun(
            workflow_id=run.workflow_id,
            company_id=run.company_id,
            tenant_id=run.tenant_id,
            earnings_date=run.earnings_date,
            status=run.status,
            hil_status=run.hil_status,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        scenario_tree: dict[str, Any] | None,
        confidence: float | None,
        cost_usd: float | None,
    ) -> None:
        """UPDATE status, scenario_tree, confidence, and cost_usd on the run.

        When status is 'hil', also sets hil_status to 'pending'.
        """
        update_values: dict[str, Any] = {
            "status": status,
            "scenario_tree": scenario_tree,
            "confidence": confidence,
            "cost_usd": cost_usd,
        }
        if status == "hil":
            update_values["hil_status"] = "pending"

        stmt = (
            update(EarningsBriefRun)
            .where(EarningsBriefRun.run_id == run_id)
            .values(**update_values)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_latest_by_company(
        self,
        company_id: UUID,
        tenant_id: UUID,
    ) -> EarningsBriefRun | None:
        """Return the most recent brief run for company+tenant, or None.

        Orders by created_at DESC so the latest brief is always returned.
        """
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
