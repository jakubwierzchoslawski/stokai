"""Event-driven score invalidation Celery consumer.

Celery task: scoring.invalidate_and_rescore
Triggered by Mode A pipeline after persist_event_record (step 5).

Steps:
1. Fetch event_exposure rows for the event.
2. Fetch geo_event.geo_regions and intensity.
3. For each affected company_id, enqueue scoring.rescore_company task.

Deduplication: processed event_ids tracked in Redis with a short TTL.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import to avoid circular imports at module level
_celery_app = None


def _get_app():
    global _celery_app
    if _celery_app is None:
        from src.config.celery_app import celery_app
        _celery_app = celery_app
    return _celery_app


# ---------------------------------------------------------------------------
# Deduplication helpers (Redis-backed)
# ---------------------------------------------------------------------------

_DEDUP_PREFIX = "scoring:invalidated:"
_DEDUP_TTL_SECONDS = 3600  # 1 hour


def _mark_processed(event_id: str) -> bool:
    """Mark event as processed. Returns True if NOT previously processed."""
    try:
        import redis
        from src.config.settings import get_settings
        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL)
        key = f"{_DEDUP_PREFIX}{event_id}"
        result = r.set(key, "1", nx=True, ex=_DEDUP_TTL_SECONDS)
        return result is not None
    except Exception as exc:
        logger.warning("Redis dedup check failed for event %s: %s", event_id, exc)
        # On Redis failure, allow processing (better to over-process than miss)
        return True


# ---------------------------------------------------------------------------
# DB access helpers (sync wrappers for Celery task)
# ---------------------------------------------------------------------------

def _fetch_event_data(event_id: str) -> tuple[list[str], list[str], int]:
    """Fetch affected company IDs, geo_regions, and intensity for an event.

    Returns:
        (company_ids, geo_regions, intensity)
    """
    import asyncio
    from sqlalchemy import text
    from src.config.settings import get_settings

    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Fetch affected company IDs from event_exposure
            result = await session.execute(
                text(
                    "SELECT DISTINCT company_id::text FROM event_exposure "
                    "WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )
            company_ids = [row[0] for row in result.fetchall()]

            # Fetch geo_regions and intensity from geo_event
            geo_result = await session.execute(
                text(
                    "SELECT geo_regions, intensity FROM geo_event "
                    "WHERE event_id = :event_id LIMIT 1"
                ),
                {"event_id": event_id},
            )
            geo_row = geo_result.fetchone()
            geo_regions = geo_row[0] if geo_row else []
            intensity = geo_row[1] if geo_row else 0

        await engine.dispose()
        return company_ids, geo_regions, intensity

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

def register_tasks(app) -> None:
    """Register scoring invalidation tasks on the Celery app."""

    @app.task(name="scoring.invalidate_and_rescore", bind=True, max_retries=3)
    def invalidate_and_rescore(self, event_id: str) -> dict[str, Any]:
        """Invalidate and re-score companies affected by a geo event.

        Args:
            event_id: string UUID of the geo event that triggered invalidation.

        Returns:
            dict with enqueued company IDs.
        """
        logger.info("scoring.invalidate_and_rescore called for event_id=%s", event_id)

        # Deduplication: skip if already processed
        if not _mark_processed(event_id):
            logger.info("Event %s already processed, skipping.", event_id)
            return {"event_id": event_id, "skipped": True, "enqueued": []}

        try:
            company_ids, geo_regions, intensity = _fetch_event_data(event_id)
        except Exception as exc:
            logger.error("Failed to fetch event data for %s: %s", event_id, exc)
            raise self.retry(exc=exc, countdown=30)

        if not company_ids:
            logger.info("No event_exposure rows for event %s — no re-score needed.", event_id)
            return {"event_id": event_id, "enqueued": []}

        enqueued = []
        for company_id in company_ids:
            app.send_task(
                "scoring.rescore_company",
                kwargs={
                    "company_id": company_id,
                    "event_id": event_id,
                    "geo_regions": geo_regions,
                    "event_intensity": intensity,
                },
            )
            enqueued.append(company_id)
            logger.debug("Enqueued rescore for company %s (event %s)", company_id, event_id)

        logger.info(
            "Enqueued %d re-score tasks for event %s.", len(enqueued), event_id
        )
        return {"event_id": event_id, "enqueued": enqueued}

    @app.task(name="scoring.rescore_company", bind=True, max_retries=3)
    def rescore_company(
        self,
        company_id: str,
        event_id: str,
        geo_regions: list[str] | None = None,
        event_intensity: int = 0,
    ) -> dict[str, Any]:
        """Re-score a single company in the context of a geo event.

        Args:
            company_id: UUID string of the company to rescore.
            event_id: UUID string of the triggering event.
            geo_regions: list of region codes affected.
            event_intensity: event intensity [1, 5].
        """
        logger.info("scoring.rescore_company company=%s event=%s", company_id, event_id)
        # Full implementation requires ScoringService and async runner;
        # stubbed here — production wiring done in scoring_service.py
        return {
            "company_id": company_id,
            "event_id": event_id,
            "status": "queued",
        }

    return invalidate_and_rescore, rescore_company
