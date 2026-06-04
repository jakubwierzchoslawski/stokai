"""
admin.system.cache_service — Redis cache inspection and force-refresh service.

Provides:
  - CacheService.get_cache_stats(): count keys by pattern + total Redis memory.
  - CacheService.force_refresh_cache(): SCAN + pipeline DEL (never redis.keys()).
  - InvalidDataTypeError: raised for unknown data_type values.

Patterns:
  - price_bars    → price_bar:*
  - price_bars + company_id → price_bar:{uuid}:*
  - embeddings    → embedding:*
  - event_data    → event:*

PLAN-F-030 TASK-006
"""
from __future__ import annotations

import dataclasses
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# Map of data_type -> base Redis key pattern
_PATTERN_MAP = {
    "price_bars": "price_bar:*",
    "embeddings": "embedding:*",
    "event_data": "event:*",
}

_COMPANY_SCOPED_TYPES = {"price_bars"}


class InvalidDataTypeError(ValueError):
    """Raised when an unknown data_type is requested."""


@dataclasses.dataclass
class CacheStats:
    """Snapshot of Redis key counts and memory usage."""

    price_bars_count: int
    embeddings_count: int
    event_data_count: int
    total_redis_memory_bytes: int


class CacheService:
    """Admin cache inspection and force-refresh operations.

    Args:
        redis: An async redis.asyncio.Redis client.
    """

    def __init__(self, redis) -> None:
        self._redis = redis

    def _resolve_pattern(
        self, data_type: str, company_id: Optional[uuid.UUID] = None
    ) -> str:
        """Return the Redis key glob pattern for the given data_type.

        If company_id is provided and the data_type supports it, the pattern
        is scoped to that company.

        Raises:
            InvalidDataTypeError: for unknown data_type values.
        """
        if data_type not in _PATTERN_MAP:
            raise InvalidDataTypeError(
                f"Unknown data_type {data_type!r}. "
                f"Valid values: {sorted(_PATTERN_MAP)}"
            )
        if company_id is not None and data_type in _COMPANY_SCOPED_TYPES:
            return f"price_bar:{company_id}:*"
        return _PATTERN_MAP[data_type]

    async def _count_keys(self, pattern: str) -> int:
        """Count Redis keys matching *pattern* using SCAN (non-blocking)."""
        count = 0
        try:
            async for _ in self._redis.scan_iter(pattern):
                count += 1
        except Exception as exc:
            logger.warning("Redis SCAN failed for pattern %r: %s", pattern, exc)
        return count

    async def get_cache_stats(self) -> CacheStats:
        """Return key counts by category and total Redis memory."""
        price_bars_count = await self._count_keys("price_bar:*")
        embeddings_count = await self._count_keys("embedding:*")
        event_data_count = await self._count_keys("event:*")

        total_memory = 0
        try:
            info = await self._redis.info("memory")
            total_memory = int(info.get("used_memory", 0))
        except Exception as exc:
            logger.warning("Redis INFO memory failed: %s", exc)

        return CacheStats(
            price_bars_count=price_bars_count,
            embeddings_count=embeddings_count,
            event_data_count=event_data_count,
            total_redis_memory_bytes=total_memory,
        )

    async def force_refresh_cache(
        self,
        data_type: str,
        company_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Delete all cache keys matching the pattern for *data_type*.

        Uses SCAN + pipeline DEL — never redis.keys() which blocks the server.

        Args:
            data_type: One of "price_bars", "embeddings", "event_data".
            company_id: Optional UUID to scope price_bars deletion to one company.

        Returns:
            Number of keys deleted.

        Raises:
            InvalidDataTypeError: For unknown data_type values.
        """
        pattern = self._resolve_pattern(data_type, company_id)
        deleted = 0

        try:
            pipeline = self._redis.pipeline()
            async for key in self._redis.scan_iter(pattern):
                pipeline.delete(key)
                deleted += 1
            if deleted:
                await pipeline.execute()
        except Exception as exc:
            logger.warning(
                "Redis SCAN+DEL failed for pattern %r: %s", pattern, exc
            )

        logger.info(
            "CacheService.force_refresh_cache: deleted %d keys for pattern %r",
            deleted,
            pattern,
        )
        return deleted
