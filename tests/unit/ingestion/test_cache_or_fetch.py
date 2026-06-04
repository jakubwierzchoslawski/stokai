"""Extended unit tests for cache hit/miss paths and TTL enforcement.

Covers AC-001 (zero external calls on cache hit), AC-002 (infinite TTL
for historical), AC-003 (infinite TTL for embeddings), AC-004 (event-driven
invalidation only for scores).

Uses fakeredis for Redis simulation and AsyncMock for the PG layer.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis
import msgpack
from unittest.mock import AsyncMock, MagicMock

from ingestion.cache_or_fetch import DataCacheOrFetch
from ingestion.redis_cache import RedisCacheLayer
from ingestion.ttl_policy import DataType, DEFAULT_TTL_REGISTRY


def _pack(value: object) -> bytes:
    return msgpack.packb(value, use_bin_type=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


def _make_cache_with_fake_redis(fake_redis_client, pg_get_return=None):
    redis_layer = RedisCacheLayer(fake_redis_client)

    pg_repo = MagicMock()
    pg_repo.get = AsyncMock(return_value=pg_get_return)
    pg_repo.set = AsyncMock()
    pg_repo.delete = AsyncMock()

    cache = DataCacheOrFetch(
        redis_layer=redis_layer,
        pg_repo=pg_repo,
        ttl_registry=DEFAULT_TTL_REGISTRY,
    )
    return cache, pg_repo


# ---------------------------------------------------------------------------
# Zero-call invariant tests (REQ-N-015 + AC-001)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_external_api_not_called_on_redis_hit(fake_redis):
    packed = _pack({"price": 42.0})
    await fake_redis.set("price_bar:AAPL:abc12345", packed)

    cache, _ = _make_cache_with_fake_redis(fake_redis)
    fetch_fn = AsyncMock(return_value={"price": 99.0})

    result = await cache.cache_or_fetch(
        key="price_bar:AAPL:abc12345",
        data_type=DataType.PRICE_BAR,
        fetch_fn=fetch_fn,
    )

    assert result == {"price": 42.0}
    fetch_fn.assert_not_called()


@pytest.mark.asyncio
async def test_external_api_not_called_on_pg_hit(fake_redis):
    packed = _pack({"price": 55.0})
    # Redis is empty; PG returns data
    cache, _ = _make_cache_with_fake_redis(fake_redis, pg_get_return=packed)
    fetch_fn = AsyncMock(return_value={"price": 99.0})

    result = await cache.cache_or_fetch(
        key="price_bar:AAPL:def98765",
        data_type=DataType.PRICE_BAR,
        fetch_fn=fetch_fn,
    )

    assert result == {"price": 55.0}
    fetch_fn.assert_not_called()


@pytest.mark.asyncio
async def test_100_identical_queries_result_in_1_external_api_call(fake_redis):
    """After the first call populates Redis, 99 subsequent calls must hit the cache."""
    cache, pg_repo = _make_cache_with_fake_redis(fake_redis, pg_get_return=None)
    call_count = 0

    async def counting_fetch_fn():
        nonlocal call_count
        call_count += 1
        return {"score": 9.5}

    key = "company_score:AAPL:latest"
    for _ in range(100):
        result = await cache.cache_or_fetch(
            key=key,
            data_type=DataType.COMPANY_SCORE,
            fetch_fn=counting_fetch_fn,
        )
        assert result == {"score": 9.5}

    assert call_count == 1, (
        f"fetch_fn was called {call_count} times; expected exactly 1"
    )


# ---------------------------------------------------------------------------
# Immutable TTL tests (AC-002, AC-003)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_historical_price_bar_stored_with_infinite_ttl_in_redis(fake_redis):
    cache, pg_repo = _make_cache_with_fake_redis(fake_redis)
    fetch_fn = AsyncMock(return_value={"close": 150.0, "date": "2020-01-02"})

    await cache.cache_or_fetch(
        key="price_bar_historical:AAPL:xyz",
        data_type=DataType.PRICE_BAR_HISTORICAL,
        fetch_fn=fetch_fn,
    )

    # Redis key must have no TTL (-1 means persistent)
    ttl = await fake_redis.ttl("price_bar_historical:AAPL:xyz")
    assert ttl == -1, "Historical price bar must have no Redis TTL"


@pytest.mark.asyncio
async def test_event_embedding_stored_with_infinite_ttl_in_redis(fake_redis):
    cache, pg_repo = _make_cache_with_fake_redis(fake_redis)
    fetch_fn = AsyncMock(return_value=[0.1, 0.2, 0.3])

    await cache.cache_or_fetch(
        key="event_embedding:evt001:abc",
        data_type=DataType.EVENT_EMBEDDING,
        fetch_fn=fetch_fn,
    )

    ttl = await fake_redis.ttl("event_embedding:evt001:abc")
    assert ttl == -1, "Event embedding must have no Redis TTL"


@pytest.mark.asyncio
async def test_price_bar_stored_with_correct_ttl_in_redis(fake_redis):
    cache, pg_repo = _make_cache_with_fake_redis(fake_redis)
    fetch_fn = AsyncMock(return_value={"price": 200.0})

    await cache.cache_or_fetch(
        key="price_bar:AAPL:abc",
        data_type=DataType.PRICE_BAR,
        fetch_fn=fetch_fn,
    )

    ttl = await fake_redis.ttl("price_bar:AAPL:abc")
    # TTL should be set to approximately 900 seconds
    assert 0 < ttl <= 900, f"Expected TTL near 900, got {ttl}"


# ---------------------------------------------------------------------------
# Event-driven invalidation — no TTL on scores (AC-004)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_company_score_stored_with_no_ttl(fake_redis):
    cache, pg_repo = _make_cache_with_fake_redis(fake_redis)
    fetch_fn = AsyncMock(return_value={"score": 8.2})

    await cache.cache_or_fetch(
        key="company_score:AAPL:latest",
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )

    ttl = await fake_redis.ttl("company_score:AAPL:latest")
    assert ttl == -1, "Company score must have no Redis TTL (event-driven invalidation only)"

    # PG set must be called with ttl_seconds=None
    pg_repo.set.assert_called_once()
    call_kwargs = pg_repo.set.call_args
    assert call_kwargs.args[3] is None or (
        len(call_kwargs.args) >= 4 and call_kwargs.args[3] is None
    ), "PG set must receive ttl_seconds=None for company_score"
