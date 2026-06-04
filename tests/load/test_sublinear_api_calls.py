"""Load tests: 100 sequential views produce exactly 1 external API call.

Verifies AC-001 (price chart TTL window) and AC-002 (fundamentals TTL window).

All tests operate at the CacheOrFetch layer using:
- fakeredis.aioredis for Redis simulation (no real Redis required)
- AsyncMock for the PostgreSQL repository (no DB connection)
- MagicMock / AsyncMock for the external API fetch_fn

Tests run in milliseconds — there is no real network or I/O.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from ingestion.cache_or_fetch import DataCacheOrFetch, build_cache_key
from ingestion.cache_telemetry import (
    CacheEvent,
    CacheOutcome,
    CacheTelemetry,
    CacheTier,
    NullCacheTelemetry,
)
from ingestion.ttl_policy import DEFAULT_TTL_REGISTRY, DataType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TrackingTelemetry(CacheTelemetry):
    """CacheTelemetry that records events in-memory for test assertions."""

    def __init__(self) -> None:
        super().__init__(redis_client=None)
        self.events: list[CacheEvent] = []

    def record(self, event: CacheEvent) -> None:  # noqa: D102
        self.events.append(event)

    def count(self, tier: CacheTier, outcome: CacheOutcome) -> int:
        return sum(
            1 for e in self.events if e.tier == tier and e.outcome == outcome
        )


def _make_cache(
    fake_redis_client: fakeredis.aioredis.FakeRedis,
    telemetry: CacheTelemetry | None = None,
) -> DataCacheOrFetch:
    """Build a DataCacheOrFetch wired to fakeredis and a no-op PG mock."""
    from ingestion.redis_cache import RedisCacheLayer

    redis_layer = RedisCacheLayer(fake_redis_client)

    pg_repo = MagicMock()
    pg_repo.get = AsyncMock(return_value=None)  # PG always misses — Redis is enough
    pg_repo.set = AsyncMock()
    pg_repo.delete = AsyncMock()

    return DataCacheOrFetch(
        redis_layer=redis_layer,
        pg_repo=pg_repo,
        ttl_registry=DEFAULT_TTL_REGISTRY,
        telemetry=telemetry or NullCacheTelemetry(),
    )


# ---------------------------------------------------------------------------
# TASK-003 / AC-001: 100 sequential price chart requests produce 1 external call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_100_sequential_price_chart_requests_produce_1_external_call():
    """100 identical PRICE_BAR requests within one TTL window → 1 external call.

    After the first miss populates Redis, the subsequent 99 requests must
    all hit the Redis tier and never invoke fetch_fn again.
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    telemetry = TrackingTelemetry()
    cache = _make_cache(fake_redis, telemetry)

    fetch_fn = AsyncMock(return_value={"price": 150.0})
    key = build_cache_key(DataType.PRICE_BAR, "AAPL", {})

    for _ in range(100):
        result = await cache.cache_or_fetch(
            key=key,
            data_type=DataType.PRICE_BAR,
            fetch_fn=fetch_fn,
        )
        assert result == {"price": 150.0}

    assert fetch_fn.call_count == 1, (
        f"fetch_fn was called {fetch_fn.call_count} times; expected exactly 1"
    )
    provider_misses = telemetry.count(CacheTier.PROVIDER, CacheOutcome.MISS)
    redis_hits = telemetry.count(CacheTier.REDIS, CacheOutcome.HIT)
    assert provider_misses == 1, (
        f"Expected 1 PROVIDER MISS, got {provider_misses}"
    )
    assert redis_hits == 99, (
        f"Expected 99 REDIS HITs, got {redis_hits}"
    )

    await fake_redis.aclose()


# ---------------------------------------------------------------------------
# TASK-003 sanity inverse: 100 different entities → 100 external calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_100_sequential_requests_different_entity_produce_100_external_calls():
    """100 requests for distinct entity_ids must each produce 1 external call.

    Validates test harness correctness — if the key strategy were wrong and
    all entities mapped to the same key, this would incorrectly pass with 1 call.
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    cache = _make_cache(fake_redis)

    fetch_fn = AsyncMock(side_effect=lambda: {"price": 0.0})
    # Provide a unique coroutine each call — side_effect must be a factory
    call_counter = [0]

    async def counting_fetch():
        call_counter[0] += 1
        return {"price": float(call_counter[0])}

    for i in range(100):
        key = build_cache_key(DataType.PRICE_BAR, f"TICKER_{i:03d}", {})
        await cache.cache_or_fetch(
            key=key,
            data_type=DataType.PRICE_BAR,
            fetch_fn=counting_fetch,
        )

    assert call_counter[0] == 100, (
        f"Expected 100 external calls for 100 distinct entities, got {call_counter[0]}"
    )

    await fake_redis.aclose()


# ---------------------------------------------------------------------------
# TASK-003 / AC-001: TTL expiry causes exactly 1 additional call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_99_requests_after_ttl_expiry_each_produce_1_external_call():
    """Simulate TTL expiry between iterations 1 and 2 → 2 total external calls.

    Iteration 1:  miss → fetch → store in Redis
    Expire the key in fakeredis
    Iteration 2:  miss (key expired) → fetch → store again
    Iterations 3-100: hit (key re-populated)

    Total external calls: 2.
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    cache = _make_cache(fake_redis)

    call_counter = [0]

    async def counting_fetch():
        call_counter[0] += 1
        return {"price": float(call_counter[0])}

    key = build_cache_key(DataType.PRICE_BAR, "AAPL", {})

    # Iteration 1 — cold miss, populates Redis
    await cache.cache_or_fetch(
        key=key,
        data_type=DataType.PRICE_BAR,
        fetch_fn=counting_fetch,
    )
    assert call_counter[0] == 1

    # Simulate TTL expiry
    await fake_redis.expire(key, 0)

    # Iteration 2 — Redis key expired → second miss
    await cache.cache_or_fetch(
        key=key,
        data_type=DataType.PRICE_BAR,
        fetch_fn=counting_fetch,
    )

    # Iterations 3-100 — should all hit Redis
    for _ in range(98):
        await cache.cache_or_fetch(
            key=key,
            data_type=DataType.PRICE_BAR,
            fetch_fn=counting_fetch,
        )

    assert call_counter[0] == 2, (
        f"Expected exactly 2 external calls (1 initial + 1 after expiry), "
        f"got {call_counter[0]}"
    )

    await fake_redis.aclose()


# ---------------------------------------------------------------------------
# TASK-003 / AC-002: 100 fundamentals views produce exactly 1 external call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fundamentals_100_views_produce_1_external_call():
    """100 identical FUNDAMENTALS requests within one TTL window → 1 external call.

    FUNDAMENTALS TTL is 86400s (24 hours); all 100 requests within that window
    should be served from Redis after the first fetch.
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    telemetry = TrackingTelemetry()
    cache = _make_cache(fake_redis, telemetry)

    call_counter = [0]

    async def counting_fetch():
        call_counter[0] += 1
        return {"eps": 6.57, "pe_ratio": 29.1}

    key = build_cache_key(DataType.FUNDAMENTALS, "AAPL", {})

    for _ in range(100):
        result = await cache.cache_or_fetch(
            key=key,
            data_type=DataType.FUNDAMENTALS,
            fetch_fn=counting_fetch,
        )
        assert result == {"eps": 6.57, "pe_ratio": 29.1}

    assert call_counter[0] == 1, (
        f"FUNDAMENTALS: fetch_fn called {call_counter[0]} times; expected 1"
    )
    provider_misses = telemetry.count(CacheTier.PROVIDER, CacheOutcome.MISS)
    assert provider_misses == 1, (
        f"Expected 1 PROVIDER MISS for FUNDAMENTALS, got {provider_misses}"
    )

    await fake_redis.aclose()
