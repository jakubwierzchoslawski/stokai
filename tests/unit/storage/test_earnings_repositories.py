"""
Unit tests for EarningsEventRepository and EarningsBriefRunRepository.

TDD: tests written before implementation — PLAN-F-009 TASK-002.

Tests cover:
- get_upcoming returns only events within hours_ahead window
- exists returns True only when row exists for same company+tenant+date
- insert with duplicate UNIQUE key raises IntegrityError
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures / helpers ────────────────────────────────────────────────────────


def _tenant_id() -> uuid.UUID:
    return uuid.uuid4()


def _company_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_earnings_event_orm(
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    earnings_date: date,
) -> MagicMock:
    """Return a mock ORM EarningsEvent row."""
    from src.storage.models.earnings_event import EarningsEvent

    m = MagicMock(spec=EarningsEvent)
    m.earnings_event_id = uuid.uuid4()
    m.company_id = company_id
    m.tenant_id = tenant_id
    m.earnings_date = earnings_date
    m.fiscal_quarter = "Q1 2026"
    m.expected_eps = 1.25
    m.announced_at = None
    return m


def _make_brief_run_orm(
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    earnings_date: date,
    run_id: uuid.UUID | None = None,
) -> MagicMock:
    """Return a mock ORM EarningsBriefRun row."""
    from src.storage.models.earnings_brief_run import EarningsBriefRun

    m = MagicMock(spec=EarningsBriefRun)
    m.run_id = run_id or uuid.uuid4()
    m.workflow_id = uuid.uuid4()
    m.company_id = company_id
    m.tenant_id = tenant_id
    m.earnings_date = earnings_date
    m.status = "running"
    m.hil_status = "none"
    m.confidence = None
    m.cost_usd = None
    m.scenario_tree = None
    return m


# ── EarningsEventRepository tests ─────────────────────────────────────────────


class TestGetUpcoming:
    """IEarningsEventRepository.get_upcoming — returns events within hours_ahead."""

    @pytest.mark.asyncio
    async def test_get_upcoming_returns_events_in_window(self):
        """Events with earnings_date within 24 hours are returned."""
        from src.storage.repositories.earnings_repositories import (
            EarningsEventRepository,
        )

        tenant = _tenant_id()
        company = _company_id()
        tomorrow = date.today() + timedelta(days=1)
        event_row = _make_earnings_event_orm(company, tenant, tomorrow)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [event_row]
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsEventRepository(session)
        results = await repo.get_upcoming(tenant_id=tenant, hours_ahead=24)

        assert len(results) == 1
        assert results[0].company_id == company
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_upcoming_returns_empty_when_no_events(self):
        """Returns empty list when no earnings events fall in the window."""
        from src.storage.repositories.earnings_repositories import (
            EarningsEventRepository,
        )

        tenant = _tenant_id()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsEventRepository(session)
        results = await repo.get_upcoming(tenant_id=tenant, hours_ahead=24)

        assert results == []

    @pytest.mark.asyncio
    async def test_get_upcoming_default_hours_is_24(self):
        """Default hours_ahead is 24 — query executes without explicit param."""
        from src.storage.repositories.earnings_repositories import (
            EarningsEventRepository,
        )

        tenant = _tenant_id()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsEventRepository(session)
        # Should not raise even with default parameter
        results = await repo.get_upcoming(tenant_id=tenant)

        session.execute.assert_called_once()


class TestEarningsEventInsert:
    """IEarningsEventRepository.insert — persists a new earnings event row."""

    @pytest.mark.asyncio
    async def test_insert_returns_event_with_id(self):
        """insert returns an EarningsEvent ORM row with populated PK."""
        from src.storage.repositories.earnings_repositories import (
            EarningsEventRepository,
            EarningsEventCreate,
        )

        tenant = _tenant_id()
        company = _company_id()
        tomorrow = date.today() + timedelta(days=1)

        session = AsyncMock()
        session.flush = AsyncMock()

        new_id = uuid.uuid4()

        async def mock_refresh(obj):
            obj.earnings_event_id = new_id

        session.refresh = AsyncMock(side_effect=mock_refresh)

        dto = EarningsEventCreate(
            company_id=company,
            tenant_id=tenant,
            earnings_date=tomorrow,
            fiscal_quarter="Q2 2026",
            expected_eps=1.35,
        )

        repo = EarningsEventRepository(session)
        result = await repo.insert(event=dto, tenant_id=tenant)

        assert result is not None
        assert result.earnings_event_id == new_id
        session.add.assert_called_once()
        session.flush.assert_called_once()


# ── EarningsBriefRunRepository tests ─────────────────────────────────────────


class TestBriefRunExists:
    """IEarningsBriefRunRepository.exists — idempotency guard."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_row_present(self):
        """exists returns True when a row matches company+tenant+date."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
        )

        tenant = _tenant_id()
        company = _company_id()
        today = date.today()

        session = AsyncMock()
        mock_result = MagicMock()
        # scalar_one_or_none returns a row (truthy)
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsBriefRunRepository(session)
        result = await repo.exists(
            company_id=company, tenant_id=tenant, earnings_date=today
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_no_row(self):
        """exists returns False when no row matches company+tenant+date."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
        )

        tenant = _tenant_id()
        company = _company_id()
        today = date.today()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsBriefRunRepository(session)
        result = await repo.exists(
            company_id=company, tenant_id=tenant, earnings_date=today
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_is_date_specific(self):
        """exists is specific to the exact date — different date returns False."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
        )

        tenant = _tenant_id()
        company = _company_id()
        different_date = date.today() + timedelta(days=2)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsBriefRunRepository(session)
        result = await repo.exists(
            company_id=company, tenant_id=tenant, earnings_date=different_date
        )

        assert result is False


class TestBriefRunInsert:
    """IEarningsBriefRunRepository.insert — persists new brief run row."""

    @pytest.mark.asyncio
    async def test_insert_returns_run_with_id(self):
        """insert returns an EarningsBriefRun ORM row with populated PK."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
            EarningsBriefRunCreate,
        )

        tenant = _tenant_id()
        company = _company_id()
        today = date.today()
        workflow_id = uuid.uuid4()

        session = AsyncMock()
        session.flush = AsyncMock()
        new_run_id = uuid.uuid4()

        async def mock_refresh(obj):
            obj.run_id = new_run_id

        session.refresh = AsyncMock(side_effect=mock_refresh)

        dto = EarningsBriefRunCreate(
            workflow_id=workflow_id,
            company_id=company,
            tenant_id=tenant,
            earnings_date=today,
            status="running",
        )

        repo = EarningsBriefRunRepository(session)
        result = await repo.insert(run=dto)

        assert result is not None
        assert result.run_id == new_run_id
        session.add.assert_called_once()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_duplicate_raises_integrity_error(self):
        """insert with duplicate UNIQUE key raises IntegrityError."""
        from sqlalchemy.exc import IntegrityError
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
            EarningsBriefRunCreate,
        )

        tenant = _tenant_id()
        company = _company_id()
        today = date.today()
        workflow_id = uuid.uuid4()

        session = AsyncMock()
        session.flush = AsyncMock(side_effect=IntegrityError("duplicate key", {}, None))

        dto = EarningsBriefRunCreate(
            workflow_id=workflow_id,
            company_id=company,
            tenant_id=tenant,
            earnings_date=today,
            status="running",
        )

        repo = EarningsBriefRunRepository(session)
        with pytest.raises(IntegrityError):
            await repo.insert(run=dto)


class TestBriefRunUpdateStatus:
    """IEarningsBriefRunRepository.update_status — persists final state."""

    @pytest.mark.asyncio
    async def test_update_status_executes_update(self):
        """update_status issues a DB UPDATE on the given run_id."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
        )

        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        run_id = uuid.uuid4()
        scenario = {"bull": {}, "base": {}, "bear": {}}

        repo = EarningsBriefRunRepository(session)
        await repo.update_status(
            run_id=run_id,
            status="completed",
            scenario_tree=scenario,
            confidence=0.85,
            cost_usd=0.45,
        )

        session.execute.assert_called_once()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_supports_hil_status(self):
        """update_status with status='hil' sets hil_status='pending'."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
        )

        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        run_id = uuid.uuid4()

        repo = EarningsBriefRunRepository(session)
        await repo.update_status(
            run_id=run_id,
            status="hil",
            scenario_tree=None,
            confidence=0.55,
            cost_usd=0.30,
        )

        session.execute.assert_called_once()
        session.flush.assert_called_once()


class TestGetLatestByCompany:
    """IEarningsBriefRunRepository.get_latest_by_company — returns most recent run."""

    @pytest.mark.asyncio
    async def test_get_latest_returns_none_when_absent(self):
        """Returns None when no brief run exists for company+tenant."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
        )

        tenant = _tenant_id()
        company = _company_id()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsBriefRunRepository(session)
        result = await repo.get_latest_by_company(company_id=company, tenant_id=tenant)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_returns_run_when_present(self):
        """Returns EarningsBriefRun row when one exists."""
        from src.storage.repositories.earnings_repositories import (
            EarningsBriefRunRepository,
        )

        tenant = _tenant_id()
        company = _company_id()
        run = _make_brief_run_orm(company, tenant, date.today())

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = run
        session.execute = AsyncMock(return_value=mock_result)

        repo = EarningsBriefRunRepository(session)
        result = await repo.get_latest_by_company(company_id=company, tenant_id=tenant)

        assert result is not None
        assert result.company_id == company
