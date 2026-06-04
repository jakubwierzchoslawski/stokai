"""Integration tests — Redis TTL values inspected at runtime (PLAN-N-011 TASK-004).

Uses fakeredis.aioredis (no real Redis needed). Writes entries through the
full RedisCacheLayer / CacheOrFetch stack and inspects the raw TTL stored in
the fake Redis to assert AC-002 and AC-003 compliance.

AC-002: Time-based data types get the correct TTL; writing without TTL raises
        MissingTTLError before the key is written.
AC-003: Immutable/event-driven types receive no TTL (-1 from fakeredis.ttl()).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock

from ingestion.cache_or_fetch import DataCacheOrFetch, build_cache_key
from ingestion.redis_cache import RedisCacheLayer
from ingestion.ttl_policy import DEFAULT_TTL_REGISTRY, DataType, TTLPolicy
from ingestion.ttl_validator import MissingTTLError, TTLValidator

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def fake_redis():
    """Provide a fresh in-process FakeRedis instance for each test."""
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.fixture
def pg_repo():
    """AsyncMock simulating the PostgreSQL cache repository (always miss)."""
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.set = AsyncMock(return_value=None)
    return repo


def _build_cache(fake_redis_client, pg_repo, ttl_registry=None) -> DataCacheOrFetch:
    redis_layer = RedisCacheLayer(fake_redis_client)
    return DataCacheOrFetch(
        redis_layer=redis_layer,
        pg_repo=pg_repo,
        ttl_registry=ttl_registry or DEFAULT_TTL_REGISTRY,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _write_entry(
    fake_redis_client,
    pg_repo,
    data_type: DataType,
    key: str,
    payload: dict,
    ttl_registry=None,
) -> None:
    """Write a cache entry through the full DataCacheOrFetch cascade."""
    cache = _build_cache(fake_redis_client, pg_repo, ttl_registry)

    async def fetch_fn():
        return payload

    await cache.cache_or_fetch(key=key, data_type=data_type, fetch_fn=fetch_fn)


# ---------------------------------------------------------------------------
# Tests — time-based data types get correct TTL
# ---------------------------------------------------------------------------


async def test_price_bar_cached_entry_has_ttl_of_900_seconds(
    fake_redis, pg_repo
) -> None:
    """PRICE_BAR must be stored with TTL between 895 and 900 seconds."""
    key = build_cache_key(DataType.PRICE_BAR, "AAPL")
    await _write_entry(fake_redis, pg_repo, DataType.PRICE_BAR, key, {"close": 150.0})

    ttl = await fake_redis.ttl(key)
    assert 895 <= ttl <= 900, f"Expected TTL ~900, got {ttl}"


async def test_fundamentals_cached_entry_has_ttl_of_86400_seconds(
    fake_redis, pg_repo
) -> None:
    """FUNDAMENTALS must be stored with TTL ~86400 seconds (24 hours)."""
    key = build_cache_key(DataType.FUNDAMENTALS, "AAPL")
    await _write_entry(fake_redis, pg_repo, DataType.FUNDAMENTALS, key, {"pe_ratio": 25.4})

    ttl = await fake_redis.ttl(key)
    assert 86395 <= ttl <= 86400, f"Expected TTL ~86400, got {ttl}"


async def test_news_event_cached_entry_has_ttl_of_3600_seconds(
    fake_redis, pg_repo
) -> None:
    """NEWS_EVENT must be stored with TTL ~3600 seconds (1 hour)."""
    key = build_cache_key(DataType.NEWS_EVENT, "evt-001")
    await _write_entry(fake_redis, pg_repo, DataType.NEWS_EVENT, key, {"headline": "test"})

    ttl = await fake_redis.ttl(key)
    assert 3595 <= ttl <= 3600, f"Expected TTL ~3600, got {ttl}"


# ---------------------------------------------------------------------------
# Tests — immutable / event-driven types have no TTL
# ---------------------------------------------------------------------------


async def test_historical_price_bar_cached_entry_has_no_expiry(
    fake_redis, pg_repo
) -> None:
    """PRICE_BAR_HISTORICAL is immutable; Redis key must have no expiry (TTL=-1)."""
    key = build_cache_key(DataType.PRICE_BAR_HISTORICAL, "AAPL", {"date": "2023-01-03"})
    await _write_entry(
        fake_redis, pg_repo, DataType.PRICE_BAR_HISTORICAL, key, {"close": 125.0}
    )

    ttl = await fake_redis.ttl(key)
    assert ttl == -1, f"Expected no expiry (-1), got {ttl}"


async def test_event_embedding_cached_entry_has_no_expiry(
    fake_redis, pg_repo
) -> None:
    """EVENT_EMBEDDING is immutable; Redis key must have no expiry (TTL=-1)."""
    key = build_cache_key(DataType.EVENT_EMBEDDING, "evt-abc")
    await _write_entry(
        fake_redis, pg_repo, DataType.EVENT_EMBEDDING, key, {"vector": [0.1, 0.2]}
    )

    ttl = await fake_redis.ttl(key)
    assert ttl == -1, f"Expected no expiry (-1), got {ttl}"


async def test_company_score_cached_entry_has_no_expiry(
    fake_redis, pg_repo
) -> None:
    """COMPANY_SCORE is event_driven; Redis key must have no expiry (TTL=-1)."""
    key = build_cache_key(DataType.COMPANY_SCORE, "AAPL")
    await _write_entry(
        fake_redis, pg_repo, DataType.COMPANY_SCORE, key, {"score": 8.3}
    )

    ttl = await fake_redis.ttl(key)
    assert ttl == -1, f"Expected no expiry (-1), got {ttl}"


# ---------------------------------------------------------------------------
# Tests — safety: MissingTTLError raised; key NOT written
# ---------------------------------------------------------------------------


async def test_redis_set_without_ttl_for_price_bar_raises_before_write(
    fake_redis, pg_repo
) -> None:
    """Direct RedisCacheLayer.set() for PRICE_BAR without TTL must raise and NOT write key."""
    layer = RedisCacheLayer(fake_redis)
    key = "price_bar:AAPL:manual"

    with pytest.raises(MissingTTLError):
        await layer.set(key, b"data", ttl_seconds=None, data_type=DataType.PRICE_BAR)

    # Key must NOT exist in Redis after the failed write
    value = await fake_redis.get(key)
    assert value is None, "Key must not exist after MissingTTLError"


# ---------------------------------------------------------------------------
# Tests — realtime mode: TTL is 5 seconds
# ---------------------------------------------------------------------------


async def test_real_time_price_bar_ttl_is_5_seconds(fake_redis, pg_repo) -> None:
    """PRICE_BAR with realtime TTL override (5s) must produce TTL between 1 and 5."""
    # Build a custom registry where PRICE_BAR has a 5-second TTL.
    realtime_registry = {
        **DEFAULT_TTL_REGISTRY,
        DataType.PRICE_BAR: TTLPolicy(
            data_type=DataType.PRICE_BAR,
            redis_ttl_seconds=5,
            pg_ttl_seconds=5,
            invalidation="time_based",
        ),
    }

    key = build_cache_key(DataType.PRICE_BAR, "MSFT", {"mode": "realtime"})
    await _write_entry(
        fake_redis, pg_repo, DataType.PRICE_BAR, key, {"close": 300.0}, realtime_registry
    )

    ttl = await fake_redis.ttl(key)
    assert 1 <= ttl <= 5, f"Expected realtime TTL 1-5, got {ttl}"
