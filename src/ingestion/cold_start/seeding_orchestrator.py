"""
SeedingOrchestrator — top-level coordinator for cold-start historical data seeding.

Sequence:
1. Resolve provider (GDELT or ACLED) from config.
2. Partition date range into monthly batches; load checkpoint state.
3. For each non-done batch: fetch → parse → insert geo_events (skip duplicates).
4. Run PriceSeeder (price_change_t1d).
5. Run EmbeddingBatchProcessor (text-embedding-3-small).
6. Run HnswIndexBuilder (HNSW index).
7. Run SeedingValidator (health checks).
8. Return SeedingResult.

Partial-failure tolerance: if a batch fails, mark it 'failed' with error_detail,
continue to next batch, raise SeedingOrchestrationError at end with summary.

Architecture Principle 1 / DIP: all collaborators are injected via constructor.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from src.data_providers.historical_event_provider import HistoricalEventProvider
from src.ingestion.cold_start.embedding_batch_processor import EmbeddingBatchProcessor
from src.ingestion.cold_start.event_parser import GeoEventCreate, parse_raw_event
from src.ingestion.cold_start.hnsw_index_builder import HnswIndexBuilder
from src.ingestion.cold_start.price_seeder import EventPriceContext, PriceSeeder
from src.ingestion.cold_start.seeding_validator import SeedingValidator
from src.ingestion.cold_start.types import (
    CheckpointState,
    RawHistoricalEvent,
    SeedingConfig,
    SeedingResult,
)
from src.storage.repositories.seeding_checkpoint_repository import (
    ISeedingCheckpointRepository,
)

logger = logging.getLogger(__name__)


class SeedingOrchestrationError(Exception):
    """Raised when one or more batches fail during seeding."""

    def __init__(self, message: str, failed_batches: list[str], result: SeedingResult) -> None:
        super().__init__(message)
        self.failed_batches = failed_batches
        self.result = result


class IGeoEventRepository(Protocol):
    """Minimal protocol for geo_event insertion (DIP)."""

    async def insert_if_not_exists(self, event: GeoEventCreate) -> bool:
        """Insert event, skip if event_id already exists.

        Returns True if inserted, False if skipped.
        """
        ...

    async def get_events_without_embeddings(self) -> list[tuple[UUID, str]]:
        """Return (event_id, summary) for events lacking an event_embedding row."""
        ...


class SeedingOrchestrator:
    """Coordinates all cold-start seeding steps.

    Args:
        checkpoint_repo: Tracks per-batch progress in DB (not in-memory).
        geo_event_repo: Writes geo_event rows (skip duplicates by event_id).
        price_seeder: Computes and writes price_change_t1d.
        embedding_processor: Generates and stores OpenAI embeddings.
        hnsw_builder: Builds or rebuilds the HNSW index.
        validator: Post-seeding health checks.
        gdelt_adapter: GdeltHistoricalAdapter instance.
        acled_adapter: AcledHistoricalAdapter instance.
        session: SQLAlchemy AsyncSession (passed to HNSW builder and validator).
    """

    def __init__(
        self,
        checkpoint_repo: ISeedingCheckpointRepository,
        geo_event_repo: IGeoEventRepository,
        price_seeder: PriceSeeder,
        embedding_processor: EmbeddingBatchProcessor,
        hnsw_builder: HnswIndexBuilder,
        validator: SeedingValidator,
        gdelt_adapter: HistoricalEventProvider,
        acled_adapter: HistoricalEventProvider,
        session: Any,
    ) -> None:
        self._checkpoint_repo = checkpoint_repo
        self._geo_event_repo = geo_event_repo
        self._price_seeder = price_seeder
        self._embedding_processor = embedding_processor
        self._hnsw_builder = hnsw_builder
        self._validator = validator
        self._gdelt_adapter = gdelt_adapter
        self._acled_adapter = acled_adapter
        self._session = session

    async def orchestrate(self, config: SeedingConfig) -> SeedingResult:
        """Execute the full seeding pipeline and return a SeedingResult.

        Args:
            config: Runtime configuration for this seeding invocation.

        Returns:
            SeedingResult with counts and any non-fatal error messages.

        Raises:
            SeedingOrchestrationError: if one or more batches failed.
        """
        if config.dry_run:
            logger.info("SeedingOrchestrator: DRY RUN mode — no DB writes will be performed.")

        provider = self._resolve_provider(config.provider)
        logger.info(
            "SeedingOrchestrator: starting seeding with provider=%s, "
            "start=%s, end=%s, dry_run=%s",
            config.provider,
            config.start_date,
            config.end_date,
            config.dry_run,
        )

        monthly_batches = list(_partition_monthly(config.start_date, config.end_date))
        logger.info("SeedingOrchestrator: %d monthly batches to process", len(monthly_batches))

        total_events_seeded = 0
        total_events_skipped = 0
        failed_batches: list[str] = []
        errors: list[str] = []
        seeded_event_contexts: list[EventPriceContext] = []

        for batch_start, batch_end in monthly_batches:
            batch_key = f"{config.provider}:{batch_start.isoformat()}:{batch_end.isoformat()}"

            # Check checkpoint
            checkpoint = await self._checkpoint_repo.get_checkpoint(batch_key)
            if checkpoint and checkpoint.state == CheckpointState.done:
                logger.debug("SeedingOrchestrator: skipping done batch %s", batch_key)
                continue

            # Mark in_progress
            await self._checkpoint_repo.upsert_checkpoint(
                batch_key=batch_key,
                state=CheckpointState.in_progress,
                meta={"started_at": datetime.now(tz=timezone.utc)},
            )

            batch_seeded = 0
            batch_skipped = 0

            try:
                for raw_batch in provider.fetch_batches(
                    start_date=batch_start,
                    end_date=batch_end,
                    batch_size=config.batch_size,
                ):
                    for raw_event in raw_batch:
                        geo_event = parse_raw_event(raw_event, tenant_id=None)
                        if not config.dry_run:
                            inserted = await self._geo_event_repo.insert_if_not_exists(geo_event)
                        else:
                            inserted = True  # dry run simulates insert

                        if inserted:
                            batch_seeded += 1
                            seeded_event_contexts.append(
                                EventPriceContext(
                                    event_id=geo_event.event_id,
                                    occurred_at=geo_event.occurred_at,
                                )
                            )
                        else:
                            batch_skipped += 1

                await self._checkpoint_repo.upsert_checkpoint(
                    batch_key=batch_key,
                    state=CheckpointState.done,
                    meta={
                        "events_seeded": batch_seeded,
                        "completed_at": datetime.now(tz=timezone.utc),
                    },
                )
                total_events_seeded += batch_seeded
                total_events_skipped += batch_skipped
                logger.info(
                    "SeedingOrchestrator: batch %s done — seeded=%d, skipped=%d",
                    batch_key,
                    batch_seeded,
                    batch_skipped,
                )

            except Exception as exc:
                error_msg = f"Batch {batch_key} failed: {exc}"
                logger.error("SeedingOrchestrator: %s", error_msg, exc_info=True)
                errors.append(error_msg)
                failed_batches.append(batch_key)
                if not config.dry_run:
                    await self._checkpoint_repo.upsert_checkpoint(
                        batch_key=batch_key,
                        state=CheckpointState.failed,
                        meta={"error_detail": str(exc)},
                    )
                # Continue to next batch (partial-failure tolerance)

        # Step 4: PriceSeeder
        exposures_created = 0
        if seeded_event_contexts and not config.dry_run:
            logger.info(
                "SeedingOrchestrator: running PriceSeeder for %d events ...",
                len(seeded_event_contexts),
            )
            exposures_created = await self._price_seeder.seed_exposures(
                seeded_event_contexts,
                dry_run=config.dry_run,
            )

        # Step 5: EmbeddingBatchProcessor
        embeddings_created = 0
        if not config.dry_run:
            logger.info("SeedingOrchestrator: running EmbeddingBatchProcessor ...")
            embed_items = await self._geo_event_repo.get_events_without_embeddings()
            if embed_items:
                embeddings_created = await self._embedding_processor.process_batch(
                    embed_items,
                    dry_run=config.dry_run,
                )

        # Step 6: HNSW index
        if not config.dry_run:
            logger.info("SeedingOrchestrator: building HNSW index ...")
            await self._hnsw_builder.rebuild(self._session)

        # Step 7: Validation
        if not config.dry_run:
            logger.info("SeedingOrchestrator: running post-seeding validation ...")
            await self._validator.validate(self._session)

        result = SeedingResult(
            events_seeded=total_events_seeded,
            events_skipped=total_events_skipped,
            embeddings_created=embeddings_created,
            exposures_created=exposures_created,
            errors=errors,
        )

        if failed_batches:
            raise SeedingOrchestrationError(
                f"Seeding completed with {len(failed_batches)} failed batch(es): "
                f"{', '.join(failed_batches)}",
                failed_batches=failed_batches,
                result=result,
            )

        logger.info(
            "SeedingOrchestrator: seeding complete — events_seeded=%d, "
            "embeddings_created=%d, exposures_created=%d",
            total_events_seeded,
            embeddings_created,
            exposures_created,
        )
        return result

    def _resolve_provider(self, provider_name: str) -> HistoricalEventProvider:
        """Return the correct HistoricalEventProvider for the given config.provider."""
        if provider_name.lower() == "acled":
            logger.info("SeedingOrchestrator: using AcledHistoricalAdapter")
            return self._acled_adapter
        logger.info("SeedingOrchestrator: using GdeltHistoricalAdapter")
        return self._gdelt_adapter


def _partition_monthly(start: date, end: date):
    """Yield (batch_start, batch_end) pairs for each calendar month in [start, end]."""
    current = date(start.year, start.month, 1)
    while current <= end:
        year, month = current.year, current.month
        last_day = monthrange(year, month)[1]
        batch_end = date(year, month, last_day)
        # Clamp to configured range
        batch_start_clamped = max(current, start)
        batch_end_clamped = min(batch_end, end)
        yield batch_start_clamped, batch_end_clamped
        # Advance to next month
        if month == 12:
            current = date(year + 1, 1, 1)
        else:
            current = date(year, month + 1, 1)
