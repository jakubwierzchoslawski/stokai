"""TDD tests for CacheOrFetch abstract base class — written before implementation.

Tests the three-tier cache cascade: Redis -> PostgreSQL -> fetch_fn.
"""

from __future__ import annotations

import pytest
import msgpack
from unittest.mock import AsyncMock, MagicMock, call

from ingestion.cache_or_fetch import DataCacheOrFetch
from ingestion.ttl_policy import DataType, DEFAULT_TTL_REGISTRY


def _pack(value: object) -> bytes:
    return msgpack.packb(value, use_bin_type=True)


def _make_cache(redis_return: bytes | None, pg_return: bytes | None) -> DataCacheOrFetch:
    """Build a DataCacheOrFetch with mocked Redis and PG layers."""
    redis_layer = MagicMock()
    redis_layer.get = AsyncMock(return_value=redis_return)
    redis_layer.set = AsyncMock()
    redis_layer.delete = AsyncMock()

    pg_repo = MagicMock()
    pg_repo.get = AsyncMock(return_value=pg_return)
    pg_repo.set = AsyncMock()
    pg_repo.delete = AsyncMock()

    return DataCacheOrFetch(
        redis_layer=redis_layer,
        pg_repo=pg_repo,
        ttl_registry=DEFAULT_TTL_REGISTRY,
    )


@pytest.mark.asyncio
async def test_redis_hit_returns_value_without_pg_or_api_call():
    """Redis hit: PG and fetch_fn must NOT be called."""
    packed = _pack({"price": 42.0})
    cache = _make_cache(redis_return=packed, pg_return=None)
    fetch_fn = AsyncMock(return_value={"price": 99.0})

    result = await cache.cache_or_fetch(
        key="price_bar:AAPL:abc12345",
        data_type=DataType.PRICE_BAR,
        fetch_fn=fetch_fn,
    )

    assert result == {"price": 42.0}
    cache._pg_repo.get.assert_not_called()
    fetch_fn.assert_not_called()


@pytest.mark.asyncio
async def test_redis_miss_pg_hit_writes_back_to_redis_and_returns_value():
    """Redis miss + PG hit: value returned, written back to Redis; fetch_fn not called."""
    packed = _pack({"price": 55.0})
    cache = _make_cache(redis_return=None, pg_return=packed)
    fetch_fn = AsyncMock(return_value={"price": 99.0})

    result = await cache.cache_or_fetch(
        key="price_bar:AAPL:abc12345",
        data_type=DataType.PRICE_BAR,
        fetch_fn=fetch_fn,
    )

    assert result == {"price": 55.0}
    fetch_fn.assert_not_called()

    # Redis write-back must have been called with the correct TTL
    policy = DEFAULT_TTL_REGISTRY[DataType.PRICE_BAR]
    cache._redis_layer.set.assert_called_once_with(
        "price_bar:AAPL:abc12345",
        packed,
        policy.redis_ttl_seconds,
    )


@pytest.mark.asyncio
async def test_redis_miss_pg_miss_calls_fetch_fn_stores_both_layers():
    """Both cache layers miss: fetch_fn called; result stored in Redis and PG."""
    cache = _make_cache(redis_return=None, pg_return=None)
    fetched = {"price": 123.0}
    fetch_fn = AsyncMock(return_value=fetched)

    result = await cache.cache_or_fetch(
        key="price_bar:AAPL:abc12345",
        data_type=DataType.PRICE_BAR,
        fetch_fn=fetch_fn,
    )

    assert result == fetched
    fetch_fn.assert_called_once()

    policy = DEFAULT_TTL_REGISTRY[DataType.PRICE_BAR]
    packed = _pack(fetched)

    cache._redis_layer.set.assert_called_once_with(
        "price_bar:AAPL:abc12345",
        packed,
        policy.redis_ttl_seconds,
    )
    cache._pg_repo.set.assert_called_once_with(
        "price_bar:AAPL:abc12345",
        DataType.PRICE_BAR.value,
        packed,
        policy.pg_ttl_seconds,
    )


@pytest.mark.asyncio
async def test_immutable_data_type_stored_with_no_expiry_in_both_layers():
    """PRICE_BAR_HISTORICAL: ttl_seconds=None must be passed to both layers."""
    cache = _make_cache(redis_return=None, pg_return=None)
    fetched = {"close": 150.0, "date": "2020-01-02"}
    fetch_fn = AsyncMock(return_value=fetched)

    await cache.cache_or_fetch(
        key="price_bar_historical:AAPL:xyz",
        data_type=DataType.PRICE_BAR_HISTORICAL,
        fetch_fn=fetch_fn,
    )

    packed = _pack(fetched)
    cache._redis_layer.set.assert_called_once_with(
        "price_bar_historical:AAPL:xyz",
        packed,
        None,  # no expiry
    )
    cache._pg_repo.set.assert_called_once_with(
        "price_bar_historical:AAPL:xyz",
        DataType.PRICE_BAR_HISTORICAL.value,
        packed,
        None,  # no expiry
    )


@pytest.mark.asyncio
async def test_event_driven_data_type_stored_with_no_expiry():
    """COMPANY_SCORE: ttl_seconds=None must be passed to both layers."""
    cache = _make_cache(redis_return=None, pg_return=None)
    fetched = {"score": 7.8}
    fetch_fn = AsyncMock(return_value=fetched)

    await cache.cache_or_fetch(
        key="company_score:AAPL:latest",
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )

    packed = _pack(fetched)
    cache._redis_layer.set.assert_called_once_with(
        "company_score:AAPL:latest",
        packed,
        None,
    )
    cache._pg_repo.set.assert_called_once_with(
        "company_score:AAPL:latest",
        DataType.COMPANY_SCORE.value,
        packed,
        None,
    )
