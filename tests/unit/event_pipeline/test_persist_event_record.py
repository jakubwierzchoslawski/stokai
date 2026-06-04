"""
Unit tests for persist_event_record (Step 5 of the Mode A Reactive Pipeline).

Tests:
  - test_persists_geo_event_and_exposures_atomically
  - test_rolls_back_on_exposure_insert_failure
  - test_returns_updated_ctx_with_event_id

All dependencies are mocked via AsyncMock so no real database is required.

PLAN-F-003 TASK-005.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.exposure_mapping import ExposureRecord, persist_event_record
from src.event_pipeline.pipeline_state import GeoEvent, GeoEventCreate, PipelineContext


def _make_geo_event_create() -> GeoEventCreate:
    return GeoEventCreate(
        headline="Flood in Southeast Asia",
        occurred_at="2024-06-01T08:00:00Z",
        geo_regions=["APAC"],
        sectors_affected=["agriculture"],
        event_intensity=4,
        sentiment="negative",
        source="gdelt",
    )


def _make_exposure_records(n: int = 2) -> list[ExposureRecord]:
    return [
        ExposureRecord(
            company_id=uuid.uuid4(),
            magnitude=0.35,
            direction=1,
            geo_weight=0.5,
            sector_match=1.0,
        )
        for _ in range(n)
    ]


def _make_ctx(
    exposures: list[ExposureRecord] | None = None,
    tenant_id: uuid.UUID | None = None,
) -> PipelineContext:
    return PipelineContext(
        tenant_id=tenant_id or uuid.uuid4(),
        geo_regions=["APAC"],
        sectors_affected=["agriculture"],
        event_intensity=4,
        sentiment="negative",
        geo_event_create=_make_geo_event_create(),
        exposures=exposures or _make_exposure_records(2),
    )


def _make_geo_event_repo(event_id: uuid.UUID | None = None) -> AsyncMock:
    """Return a mock IGeoEventRepository that returns a GeoEvent on insert."""
    returned_id = event_id or uuid.uuid4()
    geo_event = GeoEvent(
        event_id=returned_id,
        headline="Flood in Southeast Asia",
        occurred_at="2024-06-01T08:00:00Z",
        tenant_id=uuid.uuid4(),
    )
    repo = AsyncMock()
    repo.insert = AsyncMock(return_value=geo_event)
    return repo


def _make_exposure_repo() -> AsyncMock:
    """Return a mock IEventExposureRepository."""
    repo = AsyncMock()
    repo.bulk_insert = AsyncMock(return_value=None)
    return repo


@pytest.mark.asyncio
class TestPersistEventRecord:
    """persist_event_record atomically writes GeoEvent + EventExposure rows."""

    async def test_persists_geo_event_and_exposures_atomically(self) -> None:
        """Both geo_event_repo.insert and exposure_repo.bulk_insert are called once."""
        ctx = _make_ctx()
        geo_repo = _make_geo_event_repo()
        exposure_repo = _make_exposure_repo()

        await persist_event_record(ctx, geo_repo, exposure_repo)

        geo_repo.insert.assert_called_once()
        exposure_repo.bulk_insert.assert_called_once()

    async def test_returns_updated_ctx_with_event_id(self) -> None:
        """The returned context has event_id set to the value from the inserted GeoEvent."""
        assigned_id = uuid.uuid4()
        ctx = _make_ctx()
        geo_repo = _make_geo_event_repo(event_id=assigned_id)
        exposure_repo = _make_exposure_repo()

        result = await persist_event_record(ctx, geo_repo, exposure_repo)

        assert result is ctx  # same object returned
        assert result.event_id == assigned_id

    async def test_exposure_bulk_insert_receives_correct_event_id(self) -> None:
        """bulk_insert is called with the event_id returned from geo_event_repo.insert."""
        assigned_id = uuid.uuid4()
        ctx = _make_ctx()
        geo_repo = _make_geo_event_repo(event_id=assigned_id)
        exposure_repo = _make_exposure_repo()

        await persist_event_record(ctx, geo_repo, exposure_repo)

        call_args = exposure_repo.bulk_insert.call_args
        # First positional arg should be the event_id
        assert call_args[0][0] == assigned_id

    async def test_exposure_bulk_insert_receives_tenant_id(self) -> None:
        """bulk_insert is called with the tenant_id from the pipeline context."""
        tenant_id = uuid.uuid4()
        ctx = _make_ctx(tenant_id=tenant_id)
        geo_repo = _make_geo_event_repo()
        exposure_repo = _make_exposure_repo()

        await persist_event_record(ctx, geo_repo, exposure_repo)

        call_args = exposure_repo.bulk_insert.call_args
        # Third positional arg (or keyword) should be tenant_id
        assert call_args[0][2] == tenant_id or call_args[1].get("tenant_id") == tenant_id

    async def test_rolls_back_on_exposure_insert_failure(self) -> None:
        """If bulk_insert raises, the exception propagates (caller rolls back session)."""
        ctx = _make_ctx()
        geo_repo = _make_geo_event_repo()
        exposure_repo = AsyncMock()
        exposure_repo.bulk_insert = AsyncMock(side_effect=RuntimeError("DB error"))

        with pytest.raises(RuntimeError, match="DB error"):
            await persist_event_record(ctx, geo_repo, exposure_repo)

    async def test_geo_insert_receives_geo_event_create(self) -> None:
        """geo_event_repo.insert is called with the GeoEventCreate from ctx."""
        ctx = _make_ctx()
        geo_repo = _make_geo_event_repo()
        exposure_repo = _make_exposure_repo()

        await persist_event_record(ctx, geo_repo, exposure_repo)

        call_args = geo_repo.insert.call_args
        # First positional arg is the GeoEventCreate
        assert call_args[0][0] is ctx.geo_event_create
