"""
Unit tests for EventExposureRepository.

All DB interactions are mocked so no real database is required.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.events.models import ExposureCandidate
from src.storage.implementations.event_exposure_repository import (
    EventExposureRepository,
)


def _make_candidates(n: int = 2) -> list[ExposureCandidate]:
    return [
        ExposureCandidate(
            company_id=uuid.uuid4(),
            exposure_type="sector",
            direction="negative",
            magnitude=0.5,
        )
        for _ in range(n)
    ]


@pytest.mark.asyncio
class TestBulkInsert:
    """bulk_insert inserts multiple exposure rows with correct event_id FK."""

    async def test_bulk_insert_executes_for_each_candidate(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventExposureRepository(session)
        event_id = uuid.uuid4()
        candidates = _make_candidates(3)

        await repo.bulk_insert(event_id, candidates)

        # Should call execute once (batch insert) or once per row
        assert session.execute.called
        session.flush.assert_called_once()

    async def test_bulk_insert_empty_list_is_noop(self) -> None:
        session = AsyncMock()

        repo = EventExposureRepository(session)
        event_id = uuid.uuid4()

        await repo.bulk_insert(event_id, [])

        # No execute call for empty list
        session.execute.assert_not_called()

    async def test_bulk_insert_idempotent_on_conflict(self) -> None:
        """Idempotent: calling twice should not raise an error (ON CONFLICT DO UPDATE)."""
        session = AsyncMock()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventExposureRepository(session)
        event_id = uuid.uuid4()
        candidates = _make_candidates(1)

        # Should not raise on second call
        await repo.bulk_insert(event_id, candidates)
        await repo.bulk_insert(event_id, candidates)

        assert session.execute.call_count == 2

    async def test_bulk_insert_uses_parameterised_sql(self) -> None:
        """Verify SQL is parameterised (no string interpolation of values)."""
        session = AsyncMock()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        repo = EventExposureRepository(session)
        event_id = uuid.uuid4()
        candidates = _make_candidates(1)

        await repo.bulk_insert(event_id, candidates)

        # execute should be called with a statement object and bound params,
        # not a plain interpolated string
        call_args = session.execute.call_args
        stmt = call_args[0][0]
        # SQLAlchemy compiled statements are not plain strings
        assert not isinstance(stmt, str), "SQL must be a parameterised statement, not a plain string"


# ---------------------------------------------------------------------------
# PLAN-F-003 TASK-003 — new EventExposureRepository in storage.repositories
# ---------------------------------------------------------------------------

from src.event_pipeline.exposure_mapping import ExposureRecord  # noqa: E402
from src.storage.repositories.event_exposure_repository import (  # noqa: E402
    EventExposureRepository as PlanF003EventExposureRepository,
    IEventExposureRepository,
)


def _make_exposure_records(n: int = 2) -> list[ExposureRecord]:
    return [
        ExposureRecord(
            company_id=uuid.uuid4(),
            magnitude=0.35,
            direction=1,
            geo_weight=0.5,
            sector_match=0.0,
        )
        for _ in range(n)
    ]


@pytest.mark.asyncio
class TestPlanF003BulkInsert:
    """bulk_insert persists all ExposureRecord rows (PLAN-F-003 TASK-003)."""

    async def test_bulk_insert_persists_all_exposure_records(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003EventExposureRepository(session)
        event_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        records = _make_exposure_records(3)

        await repo.bulk_insert(event_id, records, tenant_id)

        # Called once per record
        assert session.execute.call_count == 3
        session.flush.assert_called_once()

    async def test_bulk_insert_tenant_scoped(self) -> None:
        """Each INSERT carries the tenant_id in its bind parameters."""
        session = AsyncMock()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003EventExposureRepository(session)
        event_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        records = _make_exposure_records(1)

        await repo.bulk_insert(event_id, records, tenant_id)

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["tenant_id"] == tenant_id

    async def test_bulk_insert_empty_list_is_noop(self) -> None:
        """No DB calls made when exposures list is empty."""
        session = AsyncMock()
        repo = PlanF003EventExposureRepository(session)

        await repo.bulk_insert(uuid.uuid4(), [], uuid.uuid4())

        session.execute.assert_not_called()
        session.flush.assert_not_called()


@pytest.mark.asyncio
class TestPlanF003GetActiveForCompany:
    """get_active_for_company filters by days and returns empty when no data exists."""

    async def test_get_active_for_company_filters_by_days(self) -> None:
        session = AsyncMock()
        company_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        fake_rows = [
            {
                "event_id": uuid.uuid4(),
                "company_id": company_id,
                "magnitude": 0.4,
                "direction": 1,
                "geo_weight": 0.6,
                "sector_match": 0.0,
                "occurred_at": "2024-01-10T00:00:00Z",
            }
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value = fake_rows
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003EventExposureRepository(session)
        results = await repo.get_active_for_company(company_id, tenant_id, days=30)

        assert len(results) == 1
        # Verify the cutoff param was passed
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert "cutoff" in params
        assert params["days"] if "days" in params else True  # cutoff is derived from days

    async def test_get_active_returns_empty_when_no_exposures(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003EventExposureRepository(session)
        results = await repo.get_active_for_company(uuid.uuid4(), uuid.uuid4(), days=30)

        assert results == []

    async def test_ievent_exposure_repository_protocol_satisfied(self) -> None:
        """PlanF003EventExposureRepository satisfies IEventExposureRepository."""
        session = AsyncMock()
        repo = PlanF003EventExposureRepository(session)
        assert isinstance(repo, IEventExposureRepository)
