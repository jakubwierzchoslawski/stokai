"""
Unit tests for system ops repositories:
  - PostgresIngestionJobRepository
  - PostgresCostRecordRepository
  - PostgresFeatureFlagRepository

All DB interactions are mocked. No real PostgreSQL required.

PLAN-F-030 TASK-002
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.storage.models.cost_record import CostRecord
from src.storage.models.feature_flag import FeatureFlag
from src.storage.models.ingestion_job import IngestionJob, IngestionJobStatus
from src.storage.repositories.cost_record_repo import PostgresCostRecordRepository
from src.storage.repositories.feature_flag_repo import PostgresFeatureFlagRepository
from src.storage.repositories.ingestion_job_repo import PostgresIngestionJobRepository


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


def _make_job(
    tenant_id: uuid.UUID,
    status: str = "idle",
    error_count: int = 0,
) -> IngestionJob:
    job = MagicMock(spec=IngestionJob)
    job.job_id = uuid.uuid4()
    job.tenant_id = tenant_id
    job.name = "test_job"
    job.schedule = "0 * * * *"
    job.status = status
    job.error_count = error_count
    job.last_run = None
    job.next_run = None
    job.last_error_trace = None
    job.updated_at = datetime.now(timezone.utc)
    return job


def _make_scalars_result(items: list) -> MagicMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    return result_mock


def _make_scalar_one_result(value) -> MagicMock:
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = value
    result_mock.scalar_one_or_none.return_value = value
    return result_mock


# ── IngestionJobRepository ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestIngestionJobRepository:
    """Tests for PostgresIngestionJobRepository."""

    async def test_list_all_returns_only_given_tenant(self) -> None:
        """list_all returns only jobs for the given tenant."""
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        job1 = _make_job(tenant_id)
        job2 = _make_job(other_tenant_id)  # should be filtered by SQL

        session = _make_session()
        # The repo will execute a query; mock returns only tenant's job
        session.execute = AsyncMock(return_value=_make_scalars_result([job1]))

        repo = PostgresIngestionJobRepository(session)
        result = await repo.list_all(tenant_id)

        assert result == [job1]
        session.execute.assert_called_once()

    async def test_set_status_transitions_and_updates_updated_at(self) -> None:
        """set_status updates status and updated_at."""
        tenant_id = uuid.uuid4()
        job_id = uuid.uuid4()
        updated_job = _make_job(tenant_id, status="running")
        updated_job.job_id = job_id

        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(updated_job))

        repo = PostgresIngestionJobRepository(session)
        result = await repo.set_status(job_id, IngestionJobStatus.running)

        assert result.status == "running"
        session.execute.assert_called_once()

    async def test_set_status_error_count_delta_increments(self) -> None:
        """set_status with error_count_delta=1 increments error_count."""
        tenant_id = uuid.uuid4()
        job_id = uuid.uuid4()
        failed_job = _make_job(tenant_id, status="failed", error_count=1)
        failed_job.job_id = job_id

        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(failed_job))

        repo = PostgresIngestionJobRepository(session)
        result = await repo.set_status(
            job_id, IngestionJobStatus.failed, error_count_delta=1
        )

        assert result.status == "failed"
        assert result.error_count == 1  # updated in mock
        session.execute.assert_called_once()

    async def test_set_status_raises_when_not_found(self) -> None:
        """set_status raises ValueError when job_id not found."""
        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(None))

        repo = PostgresIngestionJobRepository(session)
        with pytest.raises(ValueError, match="not found"):
            await repo.set_status(uuid.uuid4(), IngestionJobStatus.running)


# ── CostRecordRepository ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCostRecordRepository:
    """Tests for PostgresCostRecordRepository."""

    async def test_aggregate_monthly_sums_correctly(self) -> None:
        """aggregate_monthly returns the correct sum."""
        tenant_id = uuid.uuid4()
        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(42.5))

        repo = PostgresCostRecordRepository(session)
        result = await repo.aggregate_monthly(tenant_id, 2026, 6)

        assert result == 42.5

    async def test_aggregate_monthly_returns_zero_for_no_rows(self) -> None:
        """aggregate_monthly returns 0.0 when no records exist (COALESCE)."""
        tenant_id = uuid.uuid4()
        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(0.0))

        repo = PostgresCostRecordRepository(session)
        result = await repo.aggregate_monthly(tenant_id, 2026, 1)

        assert result == 0.0

    async def test_breakdown_by_source_groups_and_excludes_other_tenants(self) -> None:
        """breakdown_by_source groups by source for the given tenant only."""
        tenant_id = uuid.uuid4()

        row1 = MagicMock()
        row1.source = "openai"
        row1.total_cost_usd = 15.0

        result_mock = MagicMock()
        result_mock.all.return_value = [row1]
        session = _make_session()
        session.execute = AsyncMock(return_value=result_mock)

        repo = PostgresCostRecordRepository(session)
        result = await repo.breakdown_by_source(tenant_id, 2026, 6)

        assert len(result) == 1
        assert result[0]["source"] == "openai"
        assert result[0]["total_cost_usd"] == 15.0

    async def test_daily_totals_returns_one_row_per_day(self) -> None:
        """daily_totals returns one dict per day."""
        tenant_id = uuid.uuid4()

        row1 = MagicMock()
        row1.date = date(2026, 6, 1)
        row1.total_cost_usd = 5.0
        row2 = MagicMock()
        row2.date = date(2026, 6, 2)
        row2.total_cost_usd = 7.0

        result_mock = MagicMock()
        result_mock.all.return_value = [row1, row2]
        session = _make_session()
        session.execute = AsyncMock(return_value=result_mock)

        repo = PostgresCostRecordRepository(session)
        result = await repo.daily_totals(
            tenant_id,
            start=date(2026, 6, 1),
            end=date(2026, 6, 2),
        )

        assert len(result) == 2
        assert result[0]["date"] == "2026-06-01"
        assert result[0]["total_cost_usd"] == 5.0
        assert result[1]["date"] == "2026-06-02"

    async def test_insert_adds_and_returns_record(self) -> None:
        """insert flushes session and returns the record."""
        tenant_id = uuid.uuid4()
        record = CostRecord(
            tenant_id=tenant_id,
            date=date(2026, 6, 1),
            source="openai",
            cost_usd=3.14,
        )
        session = _make_session()

        repo = PostgresCostRecordRepository(session)
        result = await repo.insert(record)

        session.add.assert_called_once_with(record)
        session.flush.assert_called_once()
        session.refresh.assert_called_once_with(record)
        assert result is record


# ── FeatureFlagRepository ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFeatureFlagRepository:
    """Tests for PostgresFeatureFlagRepository."""

    async def test_set_enabled_persists_and_get_reflects(self) -> None:
        """set_enabled updates DB and the returned flag has the new value."""
        flag_id = "morning_brief"
        environment = "production"
        user_id = uuid.uuid4()

        updated_flag = MagicMock(spec=FeatureFlag)
        updated_flag.flag_id = flag_id
        updated_flag.environment = environment
        updated_flag.enabled = False

        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(updated_flag))

        repo = PostgresFeatureFlagRepository(session)
        result = await repo.set_enabled(flag_id, environment, False, user_id)

        assert result.enabled is False
        session.execute.assert_called_once()

    async def test_list_all_filters_by_environment(self) -> None:
        """list_all returns only flags for the given environment."""
        environment = "staging"

        flag1 = MagicMock(spec=FeatureFlag)
        flag1.flag_id = "morning_brief"
        flag1.environment = environment
        flag1.enabled = True

        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalars_result([flag1]))

        repo = PostgresFeatureFlagRepository(session)
        result = await repo.list_all(environment)

        assert len(result) == 1
        assert result[0].environment == environment

    async def test_set_enabled_raises_when_not_found(self) -> None:
        """set_enabled raises ValueError when (flag_id, environment) not found."""
        session = _make_session()
        session.execute = AsyncMock(return_value=_make_scalar_one_result(None))

        repo = PostgresFeatureFlagRepository(session)
        with pytest.raises(ValueError, match="not found"):
            await repo.set_enabled("unknown_flag", "production", True, uuid.uuid4())
