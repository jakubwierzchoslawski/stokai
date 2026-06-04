"""
Unit tests for GeoEventRepository.

All DB interactions are mocked via AsyncMock so no real database is required.
Each test rolls back the conceptual transaction by resetting mock state.

Includes tests for:
  - src.storage.implementations.geo_event_repository.GeoEventRepository (PLAN-F-001)
  - src.storage.repositories.geo_event_repository.GeoEventRepository (PLAN-F-003)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.models import ClassificationResult, RawEvent
from src.storage.implementations.geo_event_repository import GeoEventRepository


def _make_raw_event(tenant_id=None) -> RawEvent:
    return RawEvent(
        source_provider="gdelt",
        occurred_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        raw_payload={"title": "Test Event", "summary": "A test event summary"},
        tenant_id=tenant_id,
    )


def _make_classification() -> ClassificationResult:
    return ClassificationResult(
        category=["conflict"],
        intensity=3,
        sentiment="negative",
        geo_regions=["EMEA"],
        affected_sectors=["energy"],
        cameo_code="14",
    )


@pytest.mark.asyncio
class TestUpsertRaw:
    """upsert_raw inserts a new row and returns the generated event_id."""

    async def test_upsert_raw_returns_uuid(self) -> None:
        session = AsyncMock()
        expected_id = uuid.uuid4()

        # Mock the execute → scalar_one flow
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = expected_id
        session.execute = AsyncMock(return_value=result_mock)

        repo = GeoEventRepository(session)
        raw_event = _make_raw_event()

        event_id = await repo.upsert_raw(raw_event)

        assert event_id == expected_id
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_upsert_raw_with_tenant_id(self) -> None:
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        expected_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar_one.return_value = expected_id
        session.execute = AsyncMock(return_value=result_mock)

        repo = GeoEventRepository(session)
        raw_event = _make_raw_event(tenant_id=tenant_id)

        event_id = await repo.upsert_raw(raw_event)

        assert event_id == expected_id


@pytest.mark.asyncio
class TestPersistClassified:
    """persist_classified updates all classification fields on an existing staging row."""

    async def test_persist_classified_executes_update(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        repo = GeoEventRepository(session)
        event_id = uuid.uuid4()
        classification = _make_classification()

        await repo.persist_classified(
            event_id=event_id,
            classification=classification,
            title="Test Event",
            summary="A test event summary",
            lat=48.8566,
            lon=2.3522,
            source_provider="gdelt",
            tenant_id=None,
        )

        session.execute.assert_called_once()
        session.flush.assert_called_once()


@pytest.mark.asyncio
class TestGetById:
    """get_by_id returns None for a non-existent event_id."""

    async def test_get_by_id_returns_none_when_missing(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = GeoEventRepository(session)
        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    async def test_get_by_id_returns_row_when_present(self) -> None:
        session = AsyncMock()
        fake_row = MagicMock()
        fake_row.event_id = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_row
        session.execute = AsyncMock(return_value=result_mock)

        repo = GeoEventRepository(session)
        result = await repo.get_by_id(fake_row.event_id)

        assert result is not None


# ---------------------------------------------------------------------------
# PLAN-F-003 TASK-002 — new GeoEventRepository in storage.repositories
# ---------------------------------------------------------------------------

from src.event_pipeline.pipeline_state import GeoEvent, GeoEventCreate  # noqa: E402
from src.storage.repositories.geo_event_repository import (  # noqa: E402
    GeoEventRepository as PlanF003GeoEventRepository,
    IGeoEventRepository,
)


def _make_geo_event_create(headline: str = "Conflict in EMEA") -> GeoEventCreate:
    return GeoEventCreate(
        headline=headline,
        occurred_at="2024-01-15T12:00:00Z",
        geo_regions=["EMEA"],
        sectors_affected=["energy"],
        event_intensity=3,
        sentiment="negative",
        source="gdelt",
    )


@pytest.mark.asyncio
class TestPlanF003GeoEventRepositoryInsert:
    """insert returns a GeoEvent with an assigned event_id (PLAN-F-003 TASK-002)."""

    async def test_insert_returns_geo_event_with_id(self) -> None:
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        expected_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar_one.return_value = expected_id
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003GeoEventRepository(session)
        geo_event = await repo.insert(_make_geo_event_create(), tenant_id)

        assert isinstance(geo_event, GeoEvent)
        assert geo_event.event_id == expected_id
        assert geo_event.tenant_id == tenant_id
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_insert_passes_tenant_id_in_params(self) -> None:
        """Tenant id must appear in the SQL bind parameters."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = uuid.uuid4()
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003GeoEventRepository(session)
        await repo.insert(_make_geo_event_create(), tenant_id)

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["tenant_id"] == tenant_id


@pytest.mark.asyncio
class TestPlanF003GeoEventRepositoryGetById:
    """get_by_id is scoped to tenant_id (PLAN-F-003 TASK-002)."""

    async def test_get_by_id_scoped_to_tenant(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        row = {
            "event_id": event_id,
            "headline": "Test",
            "occurred_at": "2024-01-15T12:00:00Z",
            "tenant_id": tenant_id,
        }
        result_mock = MagicMock()
        result_mock.mappings.return_value.one_or_none.return_value = row
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003GeoEventRepository(session)
        geo_event = await repo.get_by_id(event_id, tenant_id)

        assert geo_event is not None
        assert geo_event.event_id == event_id
        # Verify tenant_id is in the SQL params
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["tenant_id"] == tenant_id

    async def test_get_by_id_returns_none_for_unknown_id(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = PlanF003GeoEventRepository(session)
        result = await repo.get_by_id(uuid.uuid4(), uuid.uuid4())

        assert result is None

    async def test_igeo_event_repository_protocol_satisfied(self) -> None:
        """PlanF003GeoEventRepository satisfies the IGeoEventRepository protocol."""
        session = AsyncMock()
        repo = PlanF003GeoEventRepository(session)
        assert isinstance(repo, IGeoEventRepository)
