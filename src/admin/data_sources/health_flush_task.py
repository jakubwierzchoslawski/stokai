"""Celery periodic task: flush Redis health counters to PostgreSQL.

PLAN-F-022 TASK-007.

Behaviour:
  1. Fetch all active ``DataSourceConfig`` source IDs from PostgreSQL.
  2. For each source, call ``health_counter.snapshot(source_id)`` to get
     current Redis counter values.
  3. Compute ``rate_limit_percent`` using the formula:
       (calls_today / (rate_limit_per_minute * 1440)) * 100
     where 1440 = minutes per day.
  4. Upsert a ``DataSourceHealthMetric`` row via ``DataSourceRepository.upsert_health``.
  5. Do NOT reset counters (reset handled by a separate midnight beat task).

Note: Counter keys for sources with ``calls_today=0`` still produce valid
rows with all-zero values.

Thread safety: Redis INCR / MGET are atomic.  Multiple Gunicorn workers will
safely aggregate counts without double-counting (PLAN-F-022 Risks note).

Registration: see ``src/config/celery_app.py`` beat schedule.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime, timezone

import redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.admin.data_sources.models import DataSourceConfig, DataSourceHealthMetric
from src.admin.data_sources.repository import DataSourceRepository
from src.config.celery_app import app as celery_app
from src.config.settings import get_settings
from src.providers.health_counter import HealthCounter


def _get_redis_client() -> redis.Redis:
    """Return a synchronous Redis client from env configuration.

    Reads CELERY_BROKER_URL from environment — no default; fail fast if absent (P-06).
    """
    url = os.environ.get("CELERY_BROKER_URL", "")
    if not url:
        raise RuntimeError(
            "CELERY_BROKER_URL is not set. "
            "Set it in .env (see .env.example) before starting the worker."
        )
    return redis.from_url(url, decode_responses=True)


def _compute_rate_limit_percent(
    calls_today: int, rate_limit_per_minute: int
) -> float:
    """Compute the rate-limit utilisation percentage.

    Formula: (calls_today / (rate_limit_per_minute * 1440)) * 100

    Parameters
    ----------
    calls_today:
        Total calls made today (from Redis counter).
    rate_limit_per_minute:
        The configured rate limit for this source.

    Returns
    -------
    A float in [0.0, 100.0+] representing utilisation percentage.
    Returns 0.0 when ``rate_limit_per_minute`` is zero (division guard).
    """
    daily_limit = rate_limit_per_minute * 1440  # 1440 minutes per day
    if daily_limit <= 0:
        return 0.0
    return (calls_today / daily_limit) * 100.0


async def _flush_health_metrics_async() -> None:
    """Async core of the flush task — runs inside an event loop from the Celery task."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    health_counter = HealthCounter(client=_get_redis_client())
    today = date.today()

    try:
        async with session_factory() as session:
            async with session.begin():
                # System-scoped: fetch ALL active sources (not per-tenant)
                # DataSourceRepository.get_all_active_sources is the non-tenant-scoped method
                # We use a minimal repo instantiation for the system-scoped call
                repo = DataSourceRepository(session=session, tenant_id=uuid.UUID(int=0))
                active_sources: list[DataSourceConfig] = await repo.get_all_active_sources()

                for source in active_sources:
                    source_id_str = str(source.id)
                    snap = health_counter.snapshot(source_id_str)

                    rate_pct = _compute_rate_limit_percent(
                        calls_today=snap["calls_today"],
                        rate_limit_per_minute=source.rate_limit_per_minute,
                    )

                    metric = DataSourceHealthMetric(
                        id=uuid.uuid4(),
                        source_id=source.id,
                        metric_date=today,
                        calls_today=snap["calls_today"],
                        rate_limit_percent=rate_pct,
                        error_count=snap["error_count"],
                        estimated_cost_usd=snap["estimated_cost_usd"],
                        updated_at=datetime.now(timezone.utc),
                    )

                    await repo.upsert_health(metric)
    finally:
        await engine.dispose()


@celery_app.task(name="src.admin.data_sources.health_flush_task.flush_health_metrics")
def flush_health_metrics() -> None:
    """Celery task: flush Redis health counters to PostgreSQL DataSourceHealthMetric rows.

    Runs every 60 seconds per the beat schedule in ``src/config/celery_app.py``.
    Does NOT reset Redis counters — reset is handled by a separate midnight task.

    Health metric formula:
      rate_limit_percent = (calls_today / (rate_limit_per_minute * 1440)) * 100
    """
    asyncio.run(_flush_health_metrics_async())
