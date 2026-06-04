"""RedisCacheLayer — TTL-aware hot-cache layer backed by Redis 7.

No business logic lives here. Serialization is the caller's responsibility.
On any Redis connection failure the layer degrades gracefully: get() returns
None (cache miss), set/delete/delete_by_pattern are no-ops. This guarantees
Redis unavailability never causes a service outage — only a latency spike
while the request falls through to PostgreSQL or the API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ingestion.ttl_policy import DataType
from ingestion.ttl_validator import MissingTTLError, TTLValidator

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisCacheLayer:
    """Thin async wrapper around redis.asyncio.Redis.

    The Redis client is injected — this class never creates its own connection.
    All public methods catch ``redis.RedisError`` and degrade gracefully.

    Args:
        redis_client: An async Redis client instance.
        validator: Optional TTLValidator instance. Defaults to TTLValidator().
            Pass ``None`` to disable validation entirely (not recommended).
    """

    def __init__(
        self,
        redis_client: "aioredis.Redis",  # noqa: F821
        validator: TTLValidator | None = None,
    ) -> None:
        self._redis = redis_client
        self._validator = validator if validator is not None else TTLValidator()

    async def get(self, key: str) -> bytes | None:
        """Return the raw bytes stored at *key*, or ``None`` on miss/unavailability.

        Args:
            key: The cache key.

        Returns:
            Raw bytes if the key exists, ``None`` otherwise.
        """
        try:
            return await self._redis.get(key)
        except Exception as exc:  # pragma: no cover — Redis connection errors
            logger.warning("Redis GET failed for key %r: %s", key, exc)
            return None

    async def set(
        self,
        key: str,
        value: bytes,
        ttl_seconds: int | None,
        data_type: DataType | None = None,
    ) -> None:
        """Store *value* at *key* with an optional TTL.

        When *data_type* is provided, the TTLValidator is invoked before the
        Redis SET. If the data type requires a TTL (invalidation='time_based')
        but *ttl_seconds* is None, a ``MissingTTLError`` is raised and the
        write is aborted — the key will NOT exist in Redis afterward.

        When *data_type* is None, validation is bypassed but a DEBUG-level
        warning is logged so the caller can be audited.

        Args:
            key: The cache key.
            value: Raw bytes to store.
            ttl_seconds: Expiry in seconds, or ``None`` for no expiry.
            data_type: The data type being stored. Enables TTL validation.

        Raises:
            MissingTTLError: When data_type is time_based and ttl_seconds is None.
        """
        if data_type is None:
            logger.debug(
                "Redis SET for key %r called without data_type; TTL validation bypassed.",
                key,
            )
        else:
            # Raises MissingTTLError before any Redis I/O if TTL is absent.
            self._validator.validate(data_type, ttl_seconds)

        try:
            if ttl_seconds is not None:
                await self._redis.set(key, value, ex=ttl_seconds)
            else:
                await self._redis.set(key, value)
        except MissingTTLError:
            raise
        except Exception as exc:  # pragma: no cover — Redis connection errors
            logger.warning("Redis SET failed for key %r: %s", key, exc)

    async def delete(self, key: str) -> None:
        """Delete *key* from Redis.

        Args:
            key: The cache key to delete.
        """
        try:
            await self._redis.delete(key)
        except Exception as exc:  # pragma: no cover — Redis connection errors
            logger.warning("Redis DELETE failed for key %r: %s", key, exc)

    async def delete_by_pattern(self, pattern: str) -> int:
        """Delete all keys matching *pattern* using SCAN + DEL.

        Args:
            pattern: A glob-style pattern (e.g. ``"company_score:AAPL:*"``).

        Returns:
            The number of keys deleted.
        """
        deleted = 0
        try:
            cursor: int = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception as exc:  # pragma: no cover — Redis connection errors
            logger.warning(
                "Redis SCAN/DEL failed for pattern %r: %s", pattern, exc
            )
        return deleted
