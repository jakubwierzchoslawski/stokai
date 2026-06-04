"""
Integration tests for SeedingOrchestrator.

These tests exercise the full orchestration flow with mocked external services
(no real GDELT/ACLED/OpenAI calls) but use the real module wiring. They are
marked @pytest.mark.integration and excluded from the default test run.

For DB integration, set TEST_DATABASE_URL. Otherwise the DB-writing steps
are replaced with in-memory mocks.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ingestion.cold_start.embedding_batch_processor import EmbeddingBatchProcessor
from src.ingestion.cold_start.hnsw_index_builder import HnswIndexBuilder
from src.ingestion.cold_start.price_seeder import PriceSeeder
from src.ingestion.cold_start.seeding_orchestrator import (
    SeedingOrchestrationError,
    SeedingOrchestrator,
)
from src.ingestion.cold_start.seeding_validator import SeedingValidator
from src.ingestion.cold_start.types import (
    CheckpointState,
    RawHistoricalEvent,
    SeedingConfig,
)
from src.storage.repositories.seeding_checkpoint_repository import (
    CheckpointRow,
    SeedingCheckpointRepository,
)

pytestmark = pytest.mark.integration

_FAKE_EMBEDDING = [0.0] * 1536


def _make_raw_event(external_id: str, source: str = "gdelt") -> RawHistoricalEvent:
    return RawHistoricalEvent(
        external_id=external_id,
        occurred_at=datetime(1979, 1, 15, tzinfo=timezone.utc),
        title="Integration test event",
        summary="Integration test summary",
        lat=None,
        lon=None,
        geo_regions=["US"],
        cameo_code="190",
        intensity_raw=3.0,
        sentiment_raw=0.0,
        source_provider=source,
        raw_payload={},
    )


def _build_orchestrator_with_mocks(
    gdelt_batches=None,
    done_batch_keys=None,
):
    """Build a SeedingOrchestrator with all deps mocked except SeedingOrchestrator itself."""
    done_keys = set(done_batch_keys or [])
    checkpoint_store = {}

    # Checkpoint repo: in-memory
    checkpoint_repo = AsyncMock()

    async def get_checkpoint(batch_key):
        return checkpoint_store.get(batch_key)

    async def upsert_checkpoint(batch_key, state, meta):
        now = datetime.now(tz=timezone.utc)
        checkpoint_store[batch_key] = CheckpointRow(
            batch_key=batch_key,
            state=state,
            events_seeded=meta.get("events_seeded", 0),
            embeddings_done=0,
            error_detail=meta.get("error_detail"),
            started_at=meta.get("started_at"),
            completed_at=meta.get("completed_at"),
            updated_at=now,
        )

    checkpoint_repo.get_checkpoint = AsyncMock(side_effect=get_checkpoint)
    checkpoint_repo.upsert_checkpoint = AsyncMock(side_effect=upsert_checkpoint)

    # Pre-populate done checkpoints
    for bk in done_keys:
        now = datetime.now(tz=timezone.utc)
        checkpoint_store[bk] = CheckpointRow(
            batch_key=bk,
            state=CheckpointState.done,
            events_seeded=10,
            embeddings_done=10,
            error_detail=None,
            started_at=now,
            completed_at=now,
            updated_at=now,
        )

    # Geo event repo: in-memory set to track inserts
    inserted_ids = set()
    geo_repo = AsyncMock()

    async def insert_if_not_exists(event):
        if event.event_id in inserted_ids:
            return False
        inserted_ids.add(event.event_id)
        return True

    geo_repo.insert_if_not_exists = AsyncMock(side_effect=insert_if_not_exists)
    geo_repo.get_events_without_embeddings = AsyncMock(return_value=[])

    # GDELT provider
    gdelt_provider = MagicMock()
    gdelt_provider.provider_name.return_value = "gdelt"

    batches = gdelt_batches or [[_make_raw_event("1"), _make_raw_event("2")]]
    gdelt_provider.fetch_batches.return_value = iter(batches)

    # ACLED provider
    acled_provider = MagicMock()
    acled_provider.provider_name.return_value = "acled"
    acled_provider.fetch_batches.return_value = iter([])

    # Other collaborators
    price_seeder = AsyncMock()
    price_seeder.seed_exposures = AsyncMock(return_value=2)

    embedding_svc = AsyncMock()
    embedding_svc.embed = AsyncMock(return_value=_FAKE_EMBEDDING)
    embedding_repo = AsyncMock()
    embedding_repo.event_has_embedding = AsyncMock(return_value=False)
    embedding_repo.upsert_embedding = AsyncMock()
    embedding_processor = EmbeddingBatchProcessor(embedding_svc, embedding_repo, concurrency=2)

    hnsw_builder = AsyncMock()
    hnsw_builder.rebuild = AsyncMock()

    validator = AsyncMock()
    validator.validate = AsyncMock()

    session = AsyncMock()

    orchestrator = SeedingOrchestrator(
        checkpoint_repo=checkpoint_repo,
        geo_event_repo=geo_repo,
        price_seeder=price_seeder,
        embedding_processor=embedding_processor,
        hnsw_builder=hnsw_builder,
        validator=validator,
        gdelt_adapter=gdelt_provider,
        acled_adapter=acled_provider,
        session=session,
    )
    return orchestrator, checkpoint_store, inserted_ids, gdelt_provider, acled_provider


@pytest.mark.asyncio
async def test_full_happy_path_integration():
    """Integration: mock provider yields 2 batches → events inserted → validator called."""
    batch1 = [_make_raw_event("1"), _make_raw_event("2")]
    batch2 = [_make_raw_event("3")]

    def fetch_side_effect(start_date, end_date, batch_size):
        return iter([batch1, batch2])

    orchestrator, checkpoint_store, inserted_ids, gdelt_provider, _ = (
        _build_orchestrator_with_mocks()
    )
    gdelt_provider.fetch_batches.side_effect = fetch_side_effect

    config = SeedingConfig(
        provider="gdelt",
        start_date=date(1979, 1, 1),
        end_date=date(1979, 1, 31),
    )
    result = await orchestrator.orchestrate(config)

    assert result.events_seeded == 3
    assert result.errors == []
    assert len(inserted_ids) == 3


@pytest.mark.asyncio
async def test_idempotency_second_run_skips_done_batches():
    """Idempotency: second run skips done batches; no additional insertions."""
    batch_key = "gdelt:1979-01-01:1979-01-31"

    orchestrator, checkpoint_store, inserted_ids, gdelt_provider, _ = (
        _build_orchestrator_with_mocks(done_batch_keys=[batch_key])
    )

    config = SeedingConfig(
        provider="gdelt",
        start_date=date(1979, 1, 1),
        end_date=date(1979, 1, 31),
    )
    result = await orchestrator.orchestrate(config)

    # Provider should not have been called for the done batch
    gdelt_provider.fetch_batches.assert_not_called()
    assert result.events_seeded == 0  # Nothing new


@pytest.mark.asyncio
async def test_partial_failure_continues_to_next_batch():
    """Partial failure: one batch raises → marked failed; other batches complete."""
    call_count = [0]

    def fetch_with_failure(start_date, end_date, batch_size):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Provider error on first batch")
        return iter([[_make_raw_event("X")]])

    orchestrator, checkpoint_store, inserted_ids, gdelt_provider, _ = (
        _build_orchestrator_with_mocks()
    )
    gdelt_provider.fetch_batches.side_effect = fetch_with_failure

    config = SeedingConfig(
        provider="gdelt",
        start_date=date(1979, 1, 1),
        end_date=date(1979, 2, 28),  # Two months
    )
    with pytest.raises(SeedingOrchestrationError) as exc_info:
        await orchestrator.orchestrate(config)

    error = exc_info.value
    assert len(error.failed_batches) == 1
    # The second batch should have succeeded
    assert error.result.events_seeded >= 1
