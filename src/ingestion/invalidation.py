"""ScoreCacheInvalidator — event-driven invalidation for computed company scores.

Company scores have no time-based TTL. They are valid indefinitely until an
explicit invalidation event (typically a geo_event) triggers recomputation.
This invalidator deletes the score from both Redis and PostgreSQL, ensuring
the next read triggers a fresh computation via the three-tier cascade.

Key format: ``"company_score:{company_id}:latest"``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ingestion.redis_cache import RedisCacheLayer
    from ingestion.pg_cache_repository import CacheEntryRepository

logger = logging.getLogger(__name__)


def _score_cache_key(company_id: str) -> str:
    """Return the canonical Redis/PG cache key for a company's latest score."""
    return f"company_score:{company_id}:latest"


class ScoreCacheInvalidator:
    """Event-driven cache invalidator for computed company scores.

    Deletes both the Redis hot-cache entry and the PostgreSQL persistent-cache
    entry for a company score. After invalidation the three-tier cascade will
    call the score computation function on the next read.

    Args:
        redis_layer: Injected ``RedisCacheLayer`` instance.
        pg_repo: Injected ``CacheEntryRepository`` instance.
    """

    def __init__(
        self,
        redis_layer: "RedisCacheLayer",
        pg_repo: "CacheEntryRepository",
    ) -> None:
        self._redis_layer = redis_layer
        self._pg_repo = pg_repo

    async def invalidate_company_score(self, company_id: str) -> None:
        """Delete the cached score for a single company.

        Removes entries from both Redis and PostgreSQL. Safe to call even if
        the entries do not exist (idempotent).

        Args:
            company_id: The company identifier (e.g. ticker symbol or UUID).
        """
        key = _score_cache_key(company_id)
        logger.info("Invalidating company score cache for %r (key=%r)", company_id, key)
        await self._redis_layer.delete(key)
        await self._pg_repo.delete(key)

    async def invalidate_scores_for_event(
        self, event_id: str, company_ids: list[str]
    ) -> None:
        """Invalidate cached scores for all companies exposed to a geo_event.

        Args:
            event_id: The event identifier (for logging only).
            company_ids: List of company identifiers whose scores are stale.
        """
        logger.info(
            "Invalidating %d company scores for event %r",
            len(company_ids),
            event_id,
        )
        for company_id in company_ids:
            await self.invalidate_company_score(company_id)
