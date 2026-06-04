"""
Unit tests for ICostRecordRepository extensions (PLAN-N-004 TASK-003).

Tests for:
  - daily_total_for_user(user_id, tenant_id, target_date) -> float
  - insert_for_workflow_run(...) -> CostRecord

All DB interactions are mocked. No real PostgreSQL required.
TDD: tests were written before the implementation.
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.storage.repositories.cost_record_repo import PostgresCostRecordRepository


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _make_scalar_one_result(value) -> MagicMock:
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = value
    return result_mock


# ── daily_total_for_user ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDailyTotalForUser:
    """Tests for PostgresCostRecordRepository.daily_total_for_user."""

    async def test_daily_total_for_user_returns_sum_of_rows(self) -> None:
        """Returns the correct sum for user A on the target date."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        target_date = date(2026, 6, 4)

        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(8.50))

        repo = PostgresCostRecordRepository(session)
        result = await repo.daily_total_for_user(user_id, tenant_id, target_date)

        assert result == pytest.approx(8.50)
        session.execute.assert_called_once()

    async def test_daily_total_for_user_excludes_other_users(self) -> None:
        """Returns only the total for user A, not user B on the same date."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        target_date = date(2026, 6, 4)

        # Mock returns user A's total only (SQL WHERE clause handles filtering)
        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(3.00))

        repo = PostgresCostRecordRepository(session)
        result = await repo.daily_total_for_user(user_id, tenant_id, target_date)

        assert result == pytest.approx(3.00)

    async def test_daily_total_for_user_excludes_other_dates(self) -> None:
        """Returns only today's sum, not yesterday's rows."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        today = date(2026, 6, 4)

        # Mock returns only today's total (SQL date filter)
        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(2.00))

        repo = PostgresCostRecordRepository(session)
        result = await repo.daily_total_for_user(user_id, tenant_id, today)

        assert result == pytest.approx(2.00)

    async def test_daily_total_for_user_returns_zero_when_no_rows(self) -> None:
        """Returns 0.0 when no cost_record rows exist for the user on the date."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        target_date = date(2026, 6, 4)

        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(0.0))

        repo = PostgresCostRecordRepository(session)
        result = await repo.daily_total_for_user(user_id, tenant_id, target_date)

        assert result == 0.0


# ── insert_for_workflow_run ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestInsertForWorkflowRun:
    """Tests for PostgresCostRecordRepository.insert_for_workflow_run."""

    async def test_insert_for_workflow_run_creates_cost_record(self) -> None:
        """insert_for_workflow_run creates and returns a CostRecord row."""
        workflow_run_id = uuid.uuid4()
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        target_date = date(2026, 6, 4)

        session = _make_session()
        repo = PostgresCostRecordRepository(session)

        result = await repo.insert_for_workflow_run(
            workflow_run_id=workflow_run_id,
            user_id=user_id,
            tenant_id=tenant_id,
            workflow_type="morning_brief",
            cost_usd=1.23,
            target_date=target_date,
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()
        # The returned record should have the correct fields
        added_record = session.add.call_args[0][0]
        assert added_record.user_id == user_id
        assert added_record.tenant_id == tenant_id
        assert added_record.workflow_run_id == workflow_run_id
        assert added_record.workflow_type == "morning_brief"
        assert added_record.cost_usd == pytest.approx(1.23)
        assert added_record.date == target_date

    async def test_insert_for_workflow_run_tenant_scoped(self) -> None:
        """The inserted cost_record row has the correct tenant_id."""
        tenant_id = uuid.uuid4()
        session = _make_session()

        repo = PostgresCostRecordRepository(session)
        await repo.insert_for_workflow_run(
            workflow_run_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            tenant_id=tenant_id,
            workflow_type="event_deep_dive",
            cost_usd=0.75,
            target_date=date(2026, 6, 4),
        )

        added_record = session.add.call_args[0][0]
        assert added_record.tenant_id == tenant_id
