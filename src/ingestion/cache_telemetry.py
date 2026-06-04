"""CacheTelemetry — per-request cache hit/miss structured logging.

Single-responsibility: emit one structured JSON log line per cache lookup and
optionally increment Redis counters for operational observability.

Usage::

    from ingestion.cache_telemetry import CacheTelemetry, NullCacheTelemetry

    # In production (inject real redis client):
    telemetry = CacheTelemetry(redis_client=redis)

    # In tests that don't need telemetry:
    telemetry = NullCacheTelemetry()

CacheTelemetry is injected into CacheOrFetch.__init__ as an optional parameter.
It never raises — logging or Redis failures must not propagate to callers.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger("ingestion.cache")


class CacheTier(StrEnum):
    """The cache tier at which a lookup was resolved (or where a miss occurred)."""

    REDIS = "redis"
    POSTGRES = "postgres"
    PROVIDER = "provider"  # external API call — the most expensive outcome


class CacheOutcome(StrEnum):
    """Whether a cache lookup was a hit (data found) or a miss (data not found)."""

    HIT = "hit"
    MISS = "miss"


@dataclass(frozen=True)
class CacheEvent:
    """Immutable record of a single cache lookup event.

    Attributes:
        cache_key: The full cache key that was looked up.
        data_type: The DataType string value for the lookup.
        tier: The tier at which the lookup was resolved.
        outcome: Whether the lookup was a hit or miss.
        request_id: Optional request ID propagated from FastAPI middleware for
            log correlation. None when called outside an HTTP request context.
    """

    cache_key: str
    data_type: str
    tier: CacheTier
    outcome: CacheOutcome
    request_id: str | None = None


class CacheTelemetry:
    """Per-request cache hit/miss telemetry.

    Emits one structured JSON log line per cache lookup event (at INFO level)
    and increments Redis counters ``cache_stats:hits:{tier}`` and
    ``cache_stats:misses:{tier}`` via INCR so that the admin endpoint can
    report aggregate hit rates without a log-aggregation stack.

    Constructor injection keeps the hot path zero-overhead when telemetry is
    not needed (use NullCacheTelemetry in that case).

    Never raises — logging or Redis failures are silently swallowed.
    """

    def __init__(self, redis_client: Any | None = None) -> None:
        """Initialise with an optional async Redis client.

        Args:
            redis_client: An aioredis-compatible client. When None, Redis
                counter increments are skipped (log emission still occurs).
        """
        self._redis = redis_client

    def record(self, event: CacheEvent) -> None:
        """Record a cache event.

        Emits a structured JSON log entry at INFO level and fires-and-forgets
        a Redis INCR to update the aggregate hit/miss counter for the tier.

        Fields logged: cache_key, data_type, tier, outcome, request_id.

        Args:
            event: The CacheEvent to record.
        """
        try:
            logger.info(
                "cache_lookup",
                extra={
                    "cache_key": event.cache_key,
                    "data_type": event.data_type,
                    "tier": str(event.tier),
                    "outcome": str(event.outcome),
                    "request_id": event.request_id,
                },
            )
        except Exception:
            pass  # logging must never break the request path

        if self._redis is not None:
            self._fire_and_forget_incr(event)

    def _fire_and_forget_incr(self, event: CacheEvent) -> None:
        """Increment the Redis hit/miss counter in a fire-and-forget task.

        Counter key format:
            cache_stats:hits:{tier}   — incremented on CacheOutcome.HIT
            cache_stats:misses:{tier} — incremented on CacheOutcome.MISS

        Silently swallows all errors so that telemetry never propagates to
        the request path.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._incr(event))
        except Exception:
            pass

    async def _incr(self, event: CacheEvent) -> None:
        """Async Redis INCR — called as a fire-and-forget task."""
        try:
            if event.outcome == CacheOutcome.HIT:
                counter_key = f"cache_stats:hits:{event.tier}"
            else:
                counter_key = f"cache_stats:misses:{event.tier}"
            await self._redis.incr(counter_key)
        except Exception:
            pass  # telemetry counter errors are non-fatal


class NullCacheTelemetry(CacheTelemetry):
    """No-op CacheTelemetry implementation.

    Used as the default in CacheOrFetch when no telemetry is injected.
    All methods are zero-cost no-ops so the hot path has no overhead.
    """

    def __init__(self) -> None:
        super().__init__(redis_client=None)

    def record(self, event: CacheEvent) -> None:  # noqa: D102
        pass  # intentional no-op
