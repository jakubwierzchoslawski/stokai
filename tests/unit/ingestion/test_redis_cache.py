"""Unit tests for RedisCacheLayer.

Uses fakeredis.aioredis for an in-process Redis simulation.
No real Redis process is started.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis

from ingestion.redis_cache import RedisCacheLayer


@pytest_asyncio.fixture
async def redis_client():
    """Provide a fake async Redis client."""
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def layer(redis_client):
    return RedisCacheLayer(redis_client)


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_returns_none_on_miss(layer):
    result = await layer.get("nonexistent_key")
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_bytes_on_hit(layer, redis_client):
    await redis_client.set("mykey", b"hello")
    result = await layer.get("mykey")
    assert result == b"hello"


# ---------------------------------------------------------------------------
# SET with TTL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redis_set_with_ttl_uses_ex_parameter(layer, redis_client):
    """SET with a numeric TTL must use EX so the key expires."""
    await layer.set("price_bar:AAPL:abc12345", b"data", ttl_seconds=900)
    # The key must exist right away
    value = await redis_client.get("price_bar:AAPL:abc12345")
    assert value == b"data"
    # And it must have a TTL set (not -1)
    ttl = await redis_client.ttl("price_bar:AAPL:abc12345")
    assert ttl > 0


@pytest.mark.asyncio
async def test_redis_set_with_none_ttl_does_not_set_expiry(layer, redis_client):
    """SET with ttl_seconds=None must NOT set any expiry (persistent key)."""
    await layer.set("immutable:AAPL:xyz", b"immutable_data", ttl_seconds=None)
    value = await redis_client.get("immutable:AAPL:xyz")
    assert value == b"immutable_data"
    # TTL of -1 means no expiry in Redis
    ttl = await redis_client.ttl("immutable:AAPL:xyz")
    assert ttl == -1


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_removes_key(layer, redis_client):
    await redis_client.set("del_key", b"data")
    await layer.delete("del_key")
    result = await redis_client.get("del_key")
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent_key_is_noop(layer):
    # Should not raise
    await layer.delete("ghost_key")


# ---------------------------------------------------------------------------
# DELETE BY PATTERN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_by_pattern_returns_count(layer, redis_client):
    await redis_client.set("company_score:AAPL:latest", b"v1")
    await redis_client.set("company_score:MSFT:latest", b"v2")
    await redis_client.set("price_bar:AAPL:x", b"v3")

    count = await layer.delete_by_pattern("company_score:*")
    assert count == 2

    # price_bar key must still exist
    assert await redis_client.get("price_bar:AAPL:x") == b"v3"


@pytest.mark.asyncio
async def test_delete_by_pattern_no_match_returns_zero(layer):
    count = await layer.delete_by_pattern("nonexistent:*")
    assert count == 0
