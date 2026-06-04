"""
seed_command.py — CLI entrypoint for cold-start historical data seeding.

Usage:
    python -m src.ingestion.cold_start.management.seed_command [OPTIONS]

Options:
    --provider [gdelt|acled]    Override SEEDING_PROVIDER env var.
    --start-date YYYY-MM-DD     Override GDELT_START_DATE env var.
    --end-date   YYYY-MM-DD     Override SEEDING_END_DATE env var (default: today).
    --dry-run                   Parse and validate but do not write to DB.

Exit codes:
    0  — Success (SeedingResult printed to stdout).
    1  — Failure (SeedingOrchestrationError; summary printed to stderr).

Security: ACLED_API_KEY is sourced from environment, never logged or printed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date

logger = logging.getLogger(__name__)


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the cold-start historical data seeding pipeline.",
        prog="python -m src.ingestion.cold_start.management.seed_command",
    )
    parser.add_argument(
        "--provider",
        choices=["gdelt", "acled"],
        default=None,
        help="Event data provider (overrides SEEDING_PROVIDER env var).",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Start date YYYY-MM-DD (overrides GDELT_START_DATE env var).",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date YYYY-MM-DD (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Parse and validate without writing to DB.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Events per batch (overrides SEEDING_BATCH_SIZE env var).",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    """Async entrypoint: build config and run orchestrator."""
    from src.config.settings import get_settings
    from src.data_providers.acled_historical_adapter import AcledHistoricalAdapter
    from src.data_providers.gdelt_historical_adapter import GdeltHistoricalAdapter
    from src.ingestion.cold_start.embedding_batch_processor import EmbeddingBatchProcessor
    from src.ingestion.cold_start.hnsw_index_builder import HnswIndexBuilder
    from src.ingestion.cold_start.price_seeder import PriceSeeder
    from src.ingestion.cold_start.seeding_orchestrator import (
        SeedingOrchestrationError,
        SeedingOrchestrator,
    )
    from src.ingestion.cold_start.seeding_validator import SeedingValidator
    from src.ingestion.cold_start.types import SeedingConfig

    settings = get_settings()

    # Resolve config: CLI args override env vars
    provider = args.provider or settings.SEEDING_PROVIDER
    start_date = (
        date.fromisoformat(args.start_date)
        if args.start_date
        else settings.GDELT_START_DATE
    )
    end_date = (
        date.fromisoformat(args.end_date) if args.end_date else date.today()
    )
    batch_size = args.batch_size or settings.SEEDING_BATCH_SIZE
    dry_run = args.dry_run

    config = SeedingConfig(
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        batch_size=batch_size,
        embedding_concurrency=settings.EMBEDDING_CONCURRENCY,
        dry_run=dry_run,
    )

    logger.info(
        "seed_command: provider=%s start=%s end=%s dry_run=%s",
        config.provider,
        config.start_date,
        config.end_date,
        config.dry_run,
    )

    # Build dependencies
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionFactory() as session:
        from src.storage.repositories.seeding_checkpoint_repository import (
            SeedingCheckpointRepository,
        )

        checkpoint_repo = SeedingCheckpointRepository(session)

        # Adapters
        gdelt_adapter = GdeltHistoricalAdapter()
        acled_adapter = AcledHistoricalAdapter(
            api_key=settings.ACLED_API_KEY or ""
        )

        # Note: PriceSeeder, EmbeddingBatchProcessor etc. require their own repos
        # which depend on the full storage layer. For MVP, these are stubbed here
        # and replaced with proper injection once storage layer is implemented.
        # The orchestrator calls them via protocol — any conforming implementation works.
        price_seeder = _build_price_seeder(session)
        embedding_processor = _build_embedding_processor(session, settings)
        hnsw_builder = HnswIndexBuilder()
        validator = SeedingValidator()
        geo_repo = _build_geo_event_repo(session)

        orchestrator = SeedingOrchestrator(
            checkpoint_repo=checkpoint_repo,
            geo_event_repo=geo_repo,
            price_seeder=price_seeder,
            embedding_processor=embedding_processor,
            hnsw_builder=hnsw_builder,
            validator=validator,
            gdelt_adapter=gdelt_adapter,
            acled_adapter=acled_adapter,
            session=session,
        )

        try:
            result = await orchestrator.orchestrate(config)
            print(
                json.dumps(
                    {
                        "status": "success",
                        "events_seeded": result.events_seeded,
                        "events_skipped": result.events_skipped,
                        "embeddings_created": result.embeddings_created,
                        "exposures_created": result.exposures_created,
                        "errors": result.errors,
                    },
                    indent=2,
                )
            )
        except SeedingOrchestrationError as exc:
            print(
                json.dumps(
                    {
                        "status": "partial_failure",
                        "failed_batches": exc.failed_batches,
                        "events_seeded": exc.result.events_seeded,
                        "errors": exc.result.errors,
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    await engine.dispose()


def _build_price_seeder(session):
    """Build a PriceSeeder with a minimal DB-backed repository implementation."""
    from src.ingestion.cold_start.price_seeder import PriceSeeder

    class _DBPriceBarRepo:
        def __init__(self, sess):
            self._sess = sess

        async def get_tracked_company_ids(self):
            from sqlalchemy import text
            result = await self._sess.execute(
                text("SELECT company_id FROM company WHERE is_tracked = true")
            )
            return [row[0] for row in result.fetchall()]

        async def get_price_bars_for_date(self, company_ids, target_date):
            from sqlalchemy import text
            from src.ingestion.cold_start.price_seeder import PriceBar
            if not company_ids:
                return []
            result = await self._sess.execute(
                text(
                    "SELECT company_id, ts, close FROM price_bar "
                    "WHERE company_id = ANY(:ids) AND DATE(ts) = :dt AND interval = '1d'"
                ),
                {"ids": company_ids, "dt": target_date},
            )
            return [PriceBar(company_id=r[0], ts=r[1], close=r[2]) for r in result.fetchall()]

    class _DBExposureRepo:
        def __init__(self, sess):
            self._sess = sess

        async def upsert_event_exposure(self, event_id, company_id, price_change_t1d):
            from sqlalchemy import text
            await self._sess.execute(
                text(
                    "INSERT INTO event_exposure (event_id, company_id, price_change_t1d) "
                    "VALUES (:eid, :cid, :pct) ON CONFLICT (event_id, company_id) DO NOTHING"
                ),
                {"eid": event_id, "cid": company_id, "pct": price_change_t1d},
            )
            await self._sess.commit()

    return PriceSeeder(
        price_bar_repo=_DBPriceBarRepo(session),
        exposure_repo=_DBExposureRepo(session),
    )


def _build_embedding_processor(session, settings):
    """Build an EmbeddingBatchProcessor with OpenAI client."""
    from src.ingestion.cold_start.embedding_batch_processor import EmbeddingBatchProcessor

    class _OpenAIEmbeddingService:
        async def embed(self, text: str) -> list[float]:
            import openai
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding

    class _DBEmbeddingRepo:
        def __init__(self, sess):
            self._sess = sess

        async def event_has_embedding(self, event_id):
            from sqlalchemy import text
            result = await self._sess.execute(
                text("SELECT 1 FROM event_embedding WHERE event_id = :eid"),
                {"eid": event_id},
            )
            return result.fetchone() is not None

        async def upsert_embedding(self, event_id, embedding):
            from sqlalchemy import text
            vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
            await self._sess.execute(
                text(
                    "INSERT INTO event_embedding (event_id, embedding) "
                    "VALUES (:eid, :emb::vector) ON CONFLICT (event_id) DO NOTHING"
                ),
                {"eid": event_id, "emb": vector_str},
            )
            await self._sess.commit()

    return EmbeddingBatchProcessor(
        embedding_service=_OpenAIEmbeddingService(),
        embedding_repo=_DBEmbeddingRepo(session),
        concurrency=settings.EMBEDDING_CONCURRENCY,
    )


def _build_geo_event_repo(session):
    """Build a GeoEventRepository with SQLAlchemy async implementation."""

    class _DBGeoEventRepo:
        def __init__(self, sess):
            self._sess = sess

        async def insert_if_not_exists(self, event):
            from sqlalchemy import text
            result = await self._sess.execute(
                text(
                    """
                    INSERT INTO geo_event
                        (event_id, occurred_at, detected_at, category, intensity,
                         title, summary, lat, lon, geo_regions, affected_sectors,
                         sentiment, cameo_code, source_provider, tenant_id, ttl)
                    VALUES
                        (:event_id, :occurred_at, :detected_at, :category, :intensity,
                         :title, :summary, :lat, :lon, :geo_regions, :affected_sectors,
                         :sentiment, :cameo_code, :source_provider, :tenant_id, NULL)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """
                ),
                {
                    "event_id": str(event.event_id),
                    "occurred_at": event.occurred_at,
                    "detected_at": event.detected_at,
                    "category": event.category,
                    "intensity": event.intensity,
                    "title": event.title,
                    "summary": event.summary,
                    "lat": event.lat,
                    "lon": event.lon,
                    "geo_regions": event.geo_regions,
                    "affected_sectors": event.affected_sectors,
                    "sentiment": event.sentiment,
                    "cameo_code": event.cameo_code,
                    "source_provider": event.source_provider,
                    "tenant_id": str(event.tenant_id) if event.tenant_id else None,
                },
            )
            await self._sess.commit()
            return result.fetchone() is not None

        async def get_events_without_embeddings(self):
            from sqlalchemy import text
            result = await self._sess.execute(
                text(
                    """
                    SELECT ge.event_id, ge.summary
                    FROM geo_event ge
                    LEFT JOIN event_embedding ee ON ge.event_id = ee.event_id
                    WHERE ee.event_id IS NULL
                      AND ge.source_provider IN ('gdelt', 'acled')
                    """
                )
            )
            return [(row[0], row[1]) for row in result.fetchall()]

    return _DBGeoEventRepo(session)


def main(argv=None) -> None:
    """Parse arguments and run the async seeding pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
