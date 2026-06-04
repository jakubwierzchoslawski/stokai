"""PerSourceRateLimiter — Redis-backed sliding-window rate limiter.

Uses a 60-second window keyed as ``"rate_limit:{source_id}:{unix_minute}"``.
Each call atomically increments the counter. If the counter exceeds the
configured ``requests_per_minute`` for the source, ``RateLimitExceeded`` is
raised with enough context for the caller to implement exponential back-off
without additional Redis calls.

This is advisory (not a distributed lock): two concurrent coroutines can both
pass before either increments. At the expected load of 1–3 ingestion workers
this is acceptable. A Redis Lua atomic increment resolves this at scale.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_KEY_EXPIRY_SECONDS = 120  # two windows; safe for cleanup


class RateLimitExceeded(Exception):
    """Raised when the per-source request rate has been exceeded.

    Attributes:
        source_id: The data source identifier.
        limit: The configured requests-per-minute limit.
        current_count: The counter value that triggered the exception.
    """

    def __init__(self, source_id: str, limit: int, current_count: int) -> None:
        self.source_id = source_id
        self.limit = limit
        self.current_count = current_count
        super().__init__(
            f"Rate limit exceeded for source {source_id!r}: "
            f"{current_count}/{limit} requests in the current window."
        )


class PerSourceRateLimiter:
    """Sliding-window rate limiter backed by Redis.

    Args:
        redis_client: Injected ``redis.asyncio.Redis`` instance.
        get_rate_limit: Async callable that returns the ``requests_per_minute``
            integer for a given ``source_id``. Called on every
            ``check_and_increment`` invocation (config may change at runtime).
    """

    def __init__(
        self,
        redis_client: "aioredis.Redis",
        get_rate_limit: Callable[[str], Awaitable[int]],
    ) -> None:
        self._redis = redis_client
        self._get_rate_limit = get_rate_limit

    def _window_key(self, source_id: str) -> str:
        """Return the Redis key for the current 60-second window."""
        unix_minute = int(time.time()) // _WINDOW_SECONDS
        return f"rate_limit:{source_id}:{unix_minute}"

    async def check_and_increment(self, source_id: str) -> None:
        """Increment the rate-limit counter and raise if limit is exceeded.

        Args:
            source_id: The data source identifier (matches ``source_config`` row).

        Raises:
            RateLimitExceeded: If the current window counter exceeds the
                configured ``requests_per_minute`` for this source.
        """
        limit = await self._get_rate_limit(source_id)
        key = self._window_key(source_id)

        # Increment first, then check — caller should handle back-off
        current_count: int = await self._redis.incr(key)
        await self._redis.expire(key, _KEY_EXPIRY_SECONDS)

        if current_count > limit:
            raise RateLimitExceeded(source_id, limit, current_count)

    async def remaining(self, source_id: str) -> int:
        """Return the number of requests remaining in the current window.

        Args:
            source_id: The data source identifier.

        Returns:
            Remaining requests (0 if limit already reached or exceeded).
        """
        limit = await self._get_rate_limit(source_id)
        key = self._window_key(source_id)

        raw = await self._redis.get(key)
        if raw is None:
            return limit

        current_count = int(raw)
        return max(0, limit - current_count)
