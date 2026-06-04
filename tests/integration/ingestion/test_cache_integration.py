"""Integration smoke test for the full three-tier cache cascade.

Exercises the complete Redis → PostgreSQL → fetch_fn flow end-to-end using:
- fakeredis.aioredis for the Redis hot-cache layer
- AsyncMock for the PostgreSQL layer (simulating PG get/set/delete behaviour)
- A counter-based fetch_fn to assert zero-redundant-call invariants

Test flow:
    1. First call:  Redis miss → PG miss  → fetch_fn called → both layers populated
    2. Second call: same key  → Redis hit → fetch_fn NOT called
    3. Force-expire the Redis key → third call: PG hit → Redis refreshed → fetch_fn NOT called
    4. Invalidate via ScoreCacheInvalidator → fourth call: fetch_fn called again
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis
import msgpack
from unittest.mock import AsyncMock, MagicMock

from ingestion.cache_or_fetch import DataCacheOrFetch
from ingestion.invalidation import ScoreCacheInvalidator
from ingestion.redis_cache import RedisCacheLayer
from ingestion.ttl_policy import DataType, DEFAULT_TTL_REGISTRY


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _pack(value: object) -> bytes:
    return msgpack.packb(value, use_bin_type=True)


@pytest_asyncio.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.fixture
def pg_storage():
    """In-memory dict simulating PG get/set/delete (no real DB)."""
    store: dict[str, bytes] = {}

    async def pg_get(key: str) -> bytes | None:
        return store.get(key)

    async def pg_set(key: str, data_type: str, value: bytes, ttl_seconds: int | None) -> None:
        store[key] = value

    async def pg_delete(key: str) -> None:
        store.pop(key, None)

    repo = MagicMock()
    repo.get = AsyncMock(side_effect=pg_get)
    repo.set = AsyncMock(side_effect=pg_set)
    repo.delete = AsyncMock(side_effect=pg_delete)
    repo._store = store
    return repo


async def _build_cache(fake_redis_client, pg_repo) -> DataCacheOrFetch:
    redis_layer = RedisCacheLayer(fake_redis_client)
    return DataCacheOrFetch(
        redis_layer=redis_layer,
        pg_repo=pg_repo,
        ttl_registry=DEFAULT_TTL_REGISTRY,
    )


@pytest.mark.asyncio
async def test_full_three_tier_cascade_end_to_end(fake_redis, pg_storage):
    """End-to-end smoke test covering all four cascade states."""

    cache = await _build_cache(fake_redis, pg_storage)
    redis_layer = RedisCacheLayer(fake_redis)

    call_count = 0
    score_key = "company_score:AAPL:latest"

    async def fetch_fn() -> dict:
        nonlocal call_count
        call_count += 1
        return {"score": 9.1, "company_id": "AAPL"}

    # -----------------------------------------------------------------------
    # Step 1: Both cache layers cold — fetch_fn must be called exactly once
    # -----------------------------------------------------------------------
    result1 = await cache.cache_or_fetch(
        key=score_key,
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )
    assert result1 == {"score": 9.1, "company_id": "AAPL"}
    assert call_count == 1, "fetch_fn must be called on first request (cold cache)"

    # Redis must now hold the value
    redis_raw = await fake_redis.get(score_key)
    assert redis_raw is not None, "Redis must be populated after first call"

    # PG must also hold the value
    pg_raw = pg_storage._store.get(score_key)
    assert pg_raw is not None, "PG must be populated after first call"

    # -----------------------------------------------------------------------
    # Step 2: Redis is warm — fetch_fn must NOT be called
    # -----------------------------------------------------------------------
    result2 = await cache.cache_or_fetch(
        key=score_key,
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )
    assert result2 == {"score": 9.1, "company_id": "AAPL"}
    assert call_count == 1, "fetch_fn must NOT be called when Redis is warm"

    # -----------------------------------------------------------------------
    # Step 3: Evict from Redis; PG is warm → fetch_fn must NOT be called
    # -----------------------------------------------------------------------
    await fake_redis.delete(score_key)

    result3 = await cache.cache_or_fetch(
        key=score_key,
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )
    assert result3 == {"score": 9.1, "company_id": "AAPL"}
    assert call_count == 1, "fetch_fn must NOT be called when PG has the value"

    # Redis must have been refreshed from PG write-back
    redis_raw_refreshed = await fake_redis.get(score_key)
    assert redis_raw_refreshed is not None, "Redis must be refreshed from PG write-back"

    # -----------------------------------------------------------------------
    # Step 4: Invalidate via ScoreCacheInvalidator → fetch_fn called again
    # -----------------------------------------------------------------------
    invalidator = ScoreCacheInvalidator(
        redis_layer=redis_layer,
        pg_repo=pg_storage,
    )
    await invalidator.invalidate_company_score("AAPL")

    # Both layers must now be empty
    assert await fake_redis.get(score_key) is None, "Redis must be cleared after invalidation"
    assert pg_storage._store.get(score_key) is None, "PG must be cleared after invalidation"

    result4 = await cache.cache_or_fetch(
        key=score_key,
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )
    assert result4 == {"score": 9.1, "company_id": "AAPL"}
    assert call_count == 2, (
        "fetch_fn must be called again after event-driven invalidation"
    )
