"""Load tests: sublinear API call growth with 1, 10, 100 concurrent users.

Verifies AC-003: external API call ratio < 0.05 with concurrent users accessing
the same underlying company data via the screener.

All tests use:
- fakeredis.aioredis for Redis simulation (shared single instance per test)
- AsyncMock for the PostgreSQL layer
- asyncio.gather for concurrent coroutine scheduling (no real threads, no HTTP)

Tests run in milliseconds.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from ingestion.cache_or_fetch import DataCacheOrFetch, build_cache_key
from ingestion.cache_telemetry import NullCacheTelemetry
from ingestion.ttl_policy import DEFAULT_TTL_REGISTRY, DataType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache(
    fake_redis_client: fakeredis.aioredis.FakeRedis,
    fetch_fn_tracker: list[int],
) -> tuple[DataCacheOrFetch, AsyncMock]:
    """Build a DataCacheOrFetch and a tracking fetch_fn.

    Returns (cache, fetch_fn). fetch_fn increments fetch_fn_tracker[0] on each call.
    """
    from ingestion.redis_cache import RedisCacheLayer

    redis_layer = RedisCacheLayer(fake_redis_client)
    pg_repo = MagicMock()
    pg_repo.get = AsyncMock(return_value=None)
    pg_repo.set = AsyncMock()
    pg_repo.delete = AsyncMock()

    cache = DataCacheOrFetch(
        redis_layer=redis_layer,
        pg_repo=pg_repo,
        ttl_registry=DEFAULT_TTL_REGISTRY,
        telemetry=NullCacheTelemetry(),
    )

    async def counting_fetch():
        fetch_fn_tracker[0] += 1
        return {"price": 150.0, "eps": 6.57}

    return cache, counting_fetch


async def _user_requests(
    cache: DataCacheOrFetch,
    fetch_fn: AsyncMock,
    entity_ids: list[str],
    n_requests: int,
) -> None:
    """Simulate one user making n_requests for the given entity_ids.

    Requests are sequential within the user coroutine but the coroutine itself
    may be scheduled concurrently with other user coroutines via asyncio.gather.
    """
    for i in range(n_requests):
        entity_id = entity_ids[i % len(entity_ids)]
        key = build_cache_key(DataType.PRICE_BAR, entity_id, {})
        await cache.cache_or_fetch(
            key=key,
            data_type=DataType.PRICE_BAR,
            fetch_fn=fetch_fn,
        )


# ---------------------------------------------------------------------------
# TASK-004 / AC-003: 1 user, 50 screener requests — hit rate >= 95%
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_1_user_50_screener_requests_external_call_ratio():
    """1 user making 50 requests for the same company set produces ratio < 0.05.

    After the cold miss on the first request, all subsequent 49 requests for
    the same entity hit Redis → ratio = 1/50 = 0.02 < 0.05.
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    tracker = [0]
    cache, fetch_fn = _make_cache(fake_redis, tracker)

    # 50 requests for the same entity (simulates screener showing same company)
    company_set = ["AAPL"]
    await _user_requests(cache, fetch_fn, company_set, n_requests=50)

    ratio = tracker[0] / 50
    assert ratio < 0.05, (
        f"1 user / 50 requests: external call ratio {ratio:.3f} >= 0.05"
    )

    await fake_redis.aclose()


# ---------------------------------------------------------------------------
# TASK-004 / AC-003: 10 concurrent users — fetch_fn.call_count <= 2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10_concurrent_users_same_company_data_ratio():
    """10 concurrent users × 5 requests each = 50 total; fetch_fn.call_count <= 2.

    All users request the same company. The first concurrent user(s) that
    cold-miss populate Redis; subsequent users (and subsequent requests) hit
    the cache. At most 2 real calls may occur due to the thundering-herd window
    on the very first concurrent miss.
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    tracker = [0]
    cache, fetch_fn = _make_cache(fake_redis, tracker)

    company_set = ["AAPL"]
    tasks = [
        _user_requests(cache, fetch_fn, company_set, n_requests=5)
        for _ in range(10)
    ]
    await asyncio.gather(*tasks)

    total_requests = 50
    ratio = tracker[0] / total_requests
    assert tracker[0] <= 2, (
        f"10 users × 5 requests: expected <= 2 external calls, got {tracker[0]}"
    )
    assert ratio < 0.05, (
        f"10 users / 50 requests: external call ratio {ratio:.3f} >= 0.05"
    )

    await fake_redis.aclose()


# ---------------------------------------------------------------------------
# TASK-004 / AC-003: 100 concurrent users — ratio < 0.05
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_100_concurrent_users_same_company_data_ratio():
    """100 concurrent users × 1 request each = 100 total; ratio < 0.05.

    Core AC-003 assertion: with 100 concurrent users all requesting the same
    company data, the number of external API calls must be < 5 (ratio < 0.05).
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    tracker = [0]
    cache, fetch_fn = _make_cache(fake_redis, tracker)

    company_set = ["AAPL"]
    tasks = [
        _user_requests(cache, fetch_fn, company_set, n_requests=1)
        for _ in range(100)
    ]
    await asyncio.gather(*tasks)

    total_requests = 100
    ratio = tracker[0] / total_requests
    assert ratio < 0.05, (
        f"100 users / 100 requests: external call ratio {ratio:.3f} >= 0.05"
    )

    await fake_redis.aclose()


# ---------------------------------------------------------------------------
# TASK-004: Sublinear growth across 1, 10, 100 user scales
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_call_growth_is_sublinear_across_scales():
    """API call count at 10 users < 10× count at 1 user; same for 10→100.

    Each scenario uses a fresh fakeredis to reset the cache. This isolates
    the per-scale cold-miss behaviour.

    Sublinear means: going from 1 to 10 users (10× users) must NOT produce
    10× API calls. Similarly 10→100 users must not produce 10× more calls.
    """
    company_set = ["AAPL"]

    # Scale: 1 user, 10 requests
    fake_redis_1 = fakeredis.aioredis.FakeRedis()
    tracker_1 = [0]
    cache_1, fetch_fn_1 = _make_cache(fake_redis_1, tracker_1)
    await asyncio.gather(*[
        _user_requests(cache_1, fetch_fn_1, company_set, n_requests=10)
        for _ in range(1)
    ])
    count_1 = tracker_1[0]
    await fake_redis_1.aclose()

    # Scale: 10 users, 1 request each
    fake_redis_10 = fakeredis.aioredis.FakeRedis()
    tracker_10 = [0]
    cache_10, fetch_fn_10 = _make_cache(fake_redis_10, tracker_10)
    await asyncio.gather(*[
        _user_requests(cache_10, fetch_fn_10, company_set, n_requests=1)
        for _ in range(10)
    ])
    count_10 = tracker_10[0]
    await fake_redis_10.aclose()

    # Scale: 100 users, 1 request each
    fake_redis_100 = fakeredis.aioredis.FakeRedis()
    tracker_100 = [0]
    cache_100, fetch_fn_100 = _make_cache(fake_redis_100, tracker_100)
    await asyncio.gather(*[
        _user_requests(cache_100, fetch_fn_100, company_set, n_requests=1)
        for _ in range(100)
    ])
    count_100 = tracker_100[0]
    await fake_redis_100.aclose()

    # Sublinear: 10× users must NOT produce 10× calls
    assert count_10 < 10 * max(count_1, 1), (
        f"API call growth 1→10 users is NOT sublinear: "
        f"count_1={count_1}, count_10={count_10}"
    )
    assert count_100 < 10 * max(count_10, 1), (
        f"API call growth 10→100 users is NOT sublinear: "
        f"count_10={count_10}, count_100={count_100}"
    )


# ---------------------------------------------------------------------------
# TASK-004: Thundering herd — 20 concurrent coroutines on same cold key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thundering_herd_single_key_concurrent_miss():
    """20 concurrent coroutines miss the same cold key simultaneously.

    Because fakeredis is single-threaded and asyncio is cooperative,
    the worst case is each coroutine observes a miss before the first
    coroutine's SET completes. In practice with cooperative scheduling the
    actual number is much lower.

    Contract:
    - At least 1 external call (the cache was cold)
    - At most 3 external calls (practical upper bound per PLAN-F-032 risks)
    - NOT 20 external calls (the cache is doing its job)

    This test documents the known advisory-lock limitation. If this bound is
    violated in CI, the fix is a Redis Lua atomic lock (noted in PLAN-F-032).
    """
    fake_redis = fakeredis.aioredis.FakeRedis()
    tracker = [0]
    cache, fetch_fn = _make_cache(fake_redis, tracker)

    key = build_cache_key(DataType.PRICE_BAR, "AAPL", {})

    # All 20 coroutines start with an empty cache — thundering herd scenario
    async def one_request():
        await cache.cache_or_fetch(
            key=key,
            data_type=DataType.PRICE_BAR,
            fetch_fn=fetch_fn,
        )

    await asyncio.gather(*[one_request() for _ in range(20)])

    assert tracker[0] >= 1, "Expected at least 1 external call (cache was cold)"
    assert tracker[0] <= 3, (
        f"Thundering herd: expected <= 3 external calls, got {tracker[0]}. "
        "Cache key sharing is not working correctly."
    )

    await fake_redis.aclose()
