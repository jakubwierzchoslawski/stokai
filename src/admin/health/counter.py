"""
admin.health.counter — Redis-backed HealthCounter for per-source call/error tracking.

Key schema (UTC date):
  health:{source_id}:{YYYYMMDD}:calls          — integer counter
  health:{source_id}:{YYYYMMDD}:errors         — integer counter
  health:{source_id}:{YYYYMMDD}:rate_limit_pct — integer × 100 (avoid float keys)

All keys carry a TTL of 25 hours on first write so they expire automatically
across the daily boundary.

get_stats() returns a HealthStats Pydantic model with:
  - calls_today
  - errors_today
  - rate_limit_pct_used  (float: stored_int / 100)
  - estimated_cost_today (calls_today × cost_per_call from COST_TIER_COST_PER_CALL)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

import redis.asyncio as aioredis
from pydantic import BaseModel

# Cost per API call by tier (USD). Adjust as pricing changes.
COST_TIER_COST_PER_CALL: dict[str, float] = {
    "free": 0.0,
    "low": 0.00001,
    "medium": 0.0001,
    "high": 0.001,
}

_TTL_SECONDS = 25 * 3600  # 25 hours


class HealthStats(BaseModel):
    """Aggregated health statistics for a single source for today (UTC)."""

    source_id: str
    calls_today: int = 0
    errors_today: int = 0
    rate_limit_pct_used: float = 0.0  # decoded from stored int/100
    estimated_cost_today: float = 0.0


class HealthCounter:
    """Redis-backed per-source call and error counter.

    Constructor injection (DIP): accepts a redis.asyncio.Redis client.
    Tests substitute fakeredis.aioredis.FakeRedis.

    Args:
        redis_client: An async Redis client instance.
        ttl_seconds:  Key TTL in seconds (override in tests for fast expiry checks).
    """

    _TTL: ClassVar[int] = _TTL_SECONDS

    def __init__(
        self,
        redis_client: aioredis.Redis,
        ttl_seconds: int = _TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    # ── Key helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    def _key(self, source_id: str, metric: str, date: str | None = None) -> str:
        d = date or self._today()
        return f"health:{source_id}:{d}:{metric}"

    # ── Write operations ──────────────────────────────────────────────────────

    async def incr_calls(self, source_id: str) -> int:
        """Increment the calls counter for today. Returns the new count.

        Sets TTL on the key on first write only (EXPIRE NX semantics via INCR
        followed by conditional EXPIRE).
        """
        key = self._key(source_id, "calls")
        count = await self._redis.incr(key)
        if count == 1:
            # First write — set TTL
            await self._redis.expire(key, self._ttl)
        return count

    async def incr_errors(self, source_id: str) -> int:
        """Increment the error counter for today. Returns the new count."""
        key = self._key(source_id, "errors")
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, self._ttl)
        return count

    async def set_rate_limit_pct(self, source_id: str, pct: float) -> None:
        """Store the rate-limit percentage usage for today.

        Stored as integer × 100 to avoid float precision issues in Redis.
        e.g. 73.5% -> stored as 7350.
        """
        key = self._key(source_id, "rate_limit_pct")
        stored_int = int(round(pct * 100))
        await self._redis.set(key, stored_int, ex=self._ttl)

    # ── Read operations ───────────────────────────────────────────────────────

    async def get_stats(self, source_id: str, cost_tier: str = "free") -> HealthStats:
        """Return aggregated health stats for a source for today.

        Returns zeros for sources with no keys (cold state — no error raised).

        Args:
            source_id: Source identifier string.
            cost_tier: Used to compute estimated_cost_today. Defaults to 'free'.
        """
        today = self._today()
        calls_key = self._key(source_id, "calls", today)
        errors_key = self._key(source_id, "errors", today)
        rate_key = self._key(source_id, "rate_limit_pct", today)

        calls_raw, errors_raw, rate_raw = await self._redis.mget(
            calls_key, errors_key, rate_key
        )

        calls_today = int(calls_raw) if calls_raw else 0
        errors_today = int(errors_raw) if errors_raw else 0
        rate_limit_pct = (int(rate_raw) / 100) if rate_raw else 0.0

        cost_per_call = COST_TIER_COST_PER_CALL.get(cost_tier, 0.0)
        estimated_cost = calls_today * cost_per_call

        return HealthStats(
            source_id=source_id,
            calls_today=calls_today,
            errors_today=errors_today,
            rate_limit_pct_used=rate_limit_pct,
            estimated_cost_today=estimated_cost,
        )
