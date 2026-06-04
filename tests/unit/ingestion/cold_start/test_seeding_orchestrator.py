"""
Unit tests for SeedingOrchestrator.

All collaborators (providers, repos, services) are mocked.
Tests cover happy path, idempotency, partial failure, provider selection, and dry_run.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.cold_start.seeding_orchestrator import (
    SeedingOrchestrationError,
    SeedingOrchestrator,
)
from src.ingestion.cold_start.types import (
    CheckpointState,
    RawHistoricalEvent,
    SeedingConfig,
)
from src.storage.repositories.seeding_checkpoint_repository import (
    CheckpointRow,
)

# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_raw_event(external_id: str = "1") -> RawHistoricalEvent:
    return RawHistoricalEvent(
        external_id=external_id,
        occurred_at=datetime(1979, 1, 15, tzinfo=timezone.utc),
        title="Test",
        summary="Test summary",
        lat=None,
        lon=None,
        geo_regions=["US"],
        cameo_code="190",
        intensity_raw=3.0,
        sentiment_raw=0.0,
        source_provider="gdelt",
        raw_payload={},
    )


def _checkpoint_row(batch_key: str, state: CheckpointState) -> CheckpointRow:
    now = datetime.now(tz=timezone.utc)
    return CheckpointRow(
        batch_key=batch_key,
        state=state,
        events_seeded=0,
        embeddings_done=0,
        error_detail=None,
        started_at=now,
        completed_at=now,
        updated_at=now,
    )


def _make_provider(batches: list[list[RawHistoricalEvent]], provider_name: str = "gdelt") -> MagicMock:
    """Build a mock HistoricalEventProvider."""
    provider = MagicMock()
    provider.provider_name.return_value = provider_name
    provider.fetch_batches.return_value = iter(batches)
    return provider


def _make_checkpoint_repo(existing_checkpoints: dict = None) -> AsyncMock:
    """Build a mock ISeedingCheckpointRepository."""
    existing = existing_checkpoints or {}
    repo = AsyncMock()

    async def get_checkpoint(batch_key):
        return existing.get(batch_key)

    async def upsert_checkpoint(batch_key, state, meta):
        existing[batch_key] = _checkpoint_row(batch_key, state)

    repo.get_checkpoint = AsyncMock(side_effect=get_checkpoint)
    repo.upsert_checkpoint = AsyncMock(side_effect=upsert_checkpoint)
    return repo


def _make_geo_event_repo(insert_results: list[bool] = None) -> AsyncMock:
    """Build a mock IGeoEventRepository."""
    repo = AsyncMock()
    results = list(insert_results or [])

    async def insert_if_not_exists(event):
        if results:
            return results.pop(0)
        return True  # default: always insert

    repo.insert_if_not_exists = AsyncMock(side_effect=insert_if_not_exists)
    repo.get_events_without_embeddings = AsyncMock(return_value=[])
    return repo


def _make_orchestrator(
    gdelt_batches=None,
    acled_batches=None,
    checkpoint_existing=None,
    geo_insert_results=None,
    embedding_side_effect=None,
) -> tuple[SeedingOrchestrator, dict]:
    """Build a fully-mocked SeedingOrchestrator and return it plus the mock components."""
    gdelt_provider = _make_provider(gdelt_batches or [], "gdelt")
    acled_provider = _make_provider(acled_batches or [], "acled")
    checkpoint_repo = _make_checkpoint_repo(checkpoint_existing or {})
    geo_repo = _make_geo_event_repo(geo_insert_results)
    price_seeder = AsyncMock()
    price_seeder.seed_exposures = AsyncMock(return_value=5)
    embedding_processor = AsyncMock()
    embedding_processor.process_batch = AsyncMock(
        side_effect=embedding_side_effect or (lambda items, dry_run=False: len(items))
    )
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
    mocks = {
        "checkpoint_repo": checkpoint_repo,
        "geo_repo": geo_repo,
        "price_seeder": price_seeder,
        "embedding_processor": embedding_processor,
        "hnsw_builder": hnsw_builder,
        "validator": validator,
        "gdelt_provider": gdelt_provider,
        "acled_provider": acled_provider,
    }
    return orchestrator, mocks


# ─── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestHappyPath:
    """Full happy-path orchestration test."""

    @pytest.mark.asyncio
    async def test_full_happy_path_two_batches(self):
        """Mock provider yields 2 batches → events inserted → index built → validator passes."""
        batch1 = [_make_raw_event("1"), _make_raw_event("2")]
        batch2 = [_make_raw_event("3")]

        # GDELT provider returns two batches
        def fetch_batches(start_date, end_date, batch_size):
            return iter([batch1, batch2])

        orchestrator, mocks = _make_orchestrator()
        mocks["gdelt_provider"].fetch_batches.side_effect = fetch_batches

        config = SeedingConfig(
            provider="gdelt",
            start_date=date(1979, 1, 1),
            end_date=date(1979, 1, 31),
            batch_size=500,
        )
        result = await orchestrator.orchestrate(config)

        assert result.events_seeded >= 1
        assert result.errors == []
        mocks["hnsw_builder"].rebuild.assert_called_once()
        mocks["validator"].validate.assert_called_once()


@pytest.mark.unit
class TestIdempotency:
    """Second run skips all done batches."""

    @pytest.mark.asyncio
    async def test_second_run_skips_done_batches(self):
        """Run orchestrator twice; second run skips done batches; event count unchanged."""
        batch_key = "gdelt:1979-01-01:1979-01-31"

        # Pre-populate checkpoint as done
        done_checkpoint = _checkpoint_row(batch_key, CheckpointState.done)
        existing_checkpoints = {batch_key: done_checkpoint}

        orchestrator, mocks = _make_orchestrator(
            checkpoint_existing=existing_checkpoints,
        )

        config = SeedingConfig(
            provider="gdelt",
            start_date=date(1979, 1, 1),
            end_date=date(1979, 1, 31),
        )
        result = await orchestrator.orchestrate(config)

        # Provider should NOT have been called since all batches are done
        mocks["gdelt_provider"].fetch_batches.assert_not_called()
        assert result.events_seeded == 0


@pytest.mark.unit
class TestPartialFailure:
    """Partial failure: one batch fails, others complete, SeedingOrchestrationError raised."""

    @pytest.mark.asyncio
    async def test_batch_failure_marked_and_error_raised_at_end(self):
        """Batch 1 fails → marked 'failed'; remaining batches continue; error raised at end."""
        call_count = [0]

        def fetch_batches_with_failure(start_date, end_date, batch_size):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Provider error on batch 1")
            return iter([[_make_raw_event("1")]])

        orchestrator, mocks = _make_orchestrator()
        mocks["gdelt_provider"].fetch_batches.side_effect = fetch_batches_with_failure

        config = SeedingConfig(
            provider="gdelt",
            start_date=date(1979, 1, 1),
            end_date=date(1979, 2, 28),  # Two months = two batches
        )
        with pytest.raises(SeedingOrchestrationError) as exc_info:
            await orchestrator.orchestrate(config)

        error = exc_info.value
        assert len(error.failed_batches) >= 1

        # Verify failed batch was marked as failed in checkpoint
        upsert_calls = mocks["checkpoint_repo"].upsert_checkpoint.call_args_list
        failed_calls = [
            c for c in upsert_calls
            if c.kwargs.get("state") == CheckpointState.failed
            or (len(c.args) > 1 and c.args[1] == CheckpointState.failed)
        ]
        assert len(failed_calls) >= 1


@pytest.mark.unit
class TestProviderSelection:
    """config.provider='acled' → AcledHistoricalAdapter used."""

    @pytest.mark.asyncio
    async def test_acled_provider_selected_when_configured(self):
        """config.provider='acled' → AcledHistoricalAdapter injected (not GDELT)."""
        orchestrator, mocks = _make_orchestrator(acled_batches=[])
        mocks["acled_provider"].fetch_batches.return_value = iter([[_make_raw_event("1")]])

        config = SeedingConfig(
            provider="acled",
            start_date=date(1979, 1, 1),
            end_date=date(1979, 1, 31),
        )
        await orchestrator.orchestrate(config)

        # ACLED provider should be called, not GDELT
        mocks["acled_provider"].fetch_batches.assert_called()
        mocks["gdelt_provider"].fetch_batches.assert_not_called()


@pytest.mark.unit
class TestDryRun:
    """dry_run=True: no DB writes; log contains 'dry run'."""

    @pytest.mark.asyncio
    async def test_dry_run_no_db_writes(self, caplog):
        """dry_run=True: no DB writes performed; log output contains 'dry run' or 'DRY RUN'."""
        import logging

        orchestrator, mocks = _make_orchestrator()
        mocks["gdelt_provider"].fetch_batches.return_value = iter([[_make_raw_event("1")]])

        config = SeedingConfig(
            provider="gdelt",
            start_date=date(1979, 1, 1),
            end_date=date(1979, 1, 31),
            dry_run=True,
        )
        with caplog.at_level(logging.INFO):
            result = await orchestrator.orchestrate(config)

        # Validate no actual DB inserts
        mocks["geo_repo"].insert_if_not_exists.assert_not_called()
        mocks["embedding_processor"].process_batch.assert_not_called()
        mocks["hnsw_builder"].rebuild.assert_not_called()
        mocks["validator"].validate.assert_not_called()

        # Log should contain 'dry run' or 'DRY RUN'
        log_text = " ".join(record.message.lower() for record in caplog.records)
        assert "dry run" in log_text or "dry_run" in log_text
