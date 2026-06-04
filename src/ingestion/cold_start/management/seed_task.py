"""
seed_task.py — Celery task wrapper for cold-start historical data seeding.

Task name: ingestion.cold_start.run_seeding
Admin-triggerable from Admin panel (System Operations section).

This task calls SeedingOrchestrator.orchestrate(config) and stores SeedingResult
as the Celery task result. Accepts the same config params as seed_command.py CLI.

Usage from Admin panel:
    celery_app.send_task(
        'ingestion.cold_start.run_seeding',
        kwargs={'provider': 'gdelt', 'start_date': '1979-01-01', 'end_date': '2024-12-31'},
    )
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from src.config.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="ingestion.cold_start.run_seeding",
    bind=True,
    max_retries=0,          # Single-run seeding; manual retry via Admin panel
    track_started=True,
    acks_late=True,         # Acknowledge only after task completes (durability)
)
def run_seeding(
    self,
    provider: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    batch_size: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the cold-start seeding pipeline as a Celery task.

    Args:
        provider: 'gdelt' or 'acled' (overrides SEEDING_PROVIDER env var).
        start_date: ISO date string 'YYYY-MM-DD' (overrides GDELT_START_DATE).
        end_date: ISO date string 'YYYY-MM-DD' (default: today).
        batch_size: Events per batch (overrides SEEDING_BATCH_SIZE).
        dry_run: If True, parse only; no DB writes.

    Returns:
        dict with SeedingResult fields (JSON-serializable for Celery result backend).
    """
    logger.info(
        "run_seeding task started: provider=%s start=%s end=%s dry_run=%s",
        provider,
        start_date,
        end_date,
        dry_run,
    )

    result_dict = asyncio.run(_run_async(
        provider=provider,
        start_date_str=start_date,
        end_date_str=end_date,
        batch_size=batch_size,
        dry_run=dry_run,
    ))
    return result_dict


async def _run_async(
    provider: str | None,
    start_date_str: str | None,
    end_date_str: str | None,
    batch_size: int | None,
    dry_run: bool,
) -> dict:
    """Async implementation of the Celery task body."""
    from src.config.settings import get_settings
    from src.data_providers.acled_historical_adapter import AcledHistoricalAdapter
    from src.data_providers.gdelt_historical_adapter import GdeltHistoricalAdapter
    from src.ingestion.cold_start.hnsw_index_builder import HnswIndexBuilder
    from src.ingestion.cold_start.management.seed_command import (
        _build_embedding_processor,
        _build_geo_event_repo,
        _build_price_seeder,
    )
    from src.ingestion.cold_start.seeding_orchestrator import (
        SeedingOrchestrationError,
        SeedingOrchestrator,
    )
    from src.ingestion.cold_start.seeding_validator import SeedingValidator
    from src.ingestion.cold_start.types import SeedingConfig
    from src.storage.repositories.seeding_checkpoint_repository import (
        SeedingCheckpointRepository,
    )
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    settings = get_settings()

    resolved_provider = provider or settings.SEEDING_PROVIDER
    resolved_start = (
        date.fromisoformat(start_date_str) if start_date_str else settings.GDELT_START_DATE
    )
    resolved_end = date.fromisoformat(end_date_str) if end_date_str else date.today()
    resolved_batch_size = batch_size or settings.SEEDING_BATCH_SIZE

    config = SeedingConfig(
        provider=resolved_provider,
        start_date=resolved_start,
        end_date=resolved_end,
        batch_size=resolved_batch_size,
        embedding_concurrency=settings.EMBEDDING_CONCURRENCY,
        dry_run=dry_run,
    )

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with SessionFactory() as session:
            orchestrator = SeedingOrchestrator(
                checkpoint_repo=SeedingCheckpointRepository(session),
                geo_event_repo=_build_geo_event_repo(session),
                price_seeder=_build_price_seeder(session),
                embedding_processor=_build_embedding_processor(session, settings),
                hnsw_builder=HnswIndexBuilder(),
                validator=SeedingValidator(),
                gdelt_adapter=GdeltHistoricalAdapter(),
                acled_adapter=AcledHistoricalAdapter(api_key=settings.ACLED_API_KEY or ""),
                session=session,
            )

            try:
                result = await orchestrator.orchestrate(config)
                return {
                    "status": "success",
                    "events_seeded": result.events_seeded,
                    "events_skipped": result.events_skipped,
                    "embeddings_created": result.embeddings_created,
                    "exposures_created": result.exposures_created,
                    "errors": result.errors,
                }
            except SeedingOrchestrationError as exc:
                logger.error("run_seeding: partial failure — %s", exc)
                return {
                    "status": "partial_failure",
                    "failed_batches": exc.failed_batches,
                    "events_seeded": exc.result.events_seeded,
                    "errors": exc.result.errors,
                }
    finally:
        await engine.dispose()
