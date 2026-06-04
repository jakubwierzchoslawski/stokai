"""Acceptance tests — price freshness mode switch via config (PLAN-N-011 TASK-006).

Verifies AC-004: changing the price_freshness_mode admin flag causes the next
fetch to use the new TTL without any code change or service restart.

Uses:
  - AsyncMock for the get_source_config callable injected into PriceModeSelector
  - fakeredis.aioredis for Redis writes so actual TTL values can be inspected
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock

from ingestion.cache_or_fetch import DataCacheOrFetch, build_cache_key
from ingestion.price_mode_selector import PriceFreshnessMode, PriceModeSelector
from ingestion.redis_cache import RedisCacheLayer
from ingestion.ttl_policy import DEFAULT_TTL_REGISTRY, DataType, TTLPolicy

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.fixture
def pg_repo():
    """AsyncMock for the PostgreSQL layer — always returns cache miss."""
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.set = AsyncMock(return_value=None)
    return repo


def _build_cache_with_ttl(fake_redis_client, pg_repo, price_ttl: int) -> DataCacheOrFetch:
    """Build a DataCacheOrFetch with PRICE_BAR TTL overridden to price_ttl."""
    custom_registry = {
        **DEFAULT_TTL_REGISTRY,
        DataType.PRICE_BAR: TTLPolicy(
            data_type=DataType.PRICE_BAR,
            redis_ttl_seconds=price_ttl,
            pg_ttl_seconds=price_ttl,
            invalidation="time_based",
        ),
    }
    redis_layer = RedisCacheLayer(fake_redis_client)
    return DataCacheOrFetch(
        redis_layer=redis_layer,
        pg_repo=pg_repo,
        ttl_registry=custom_registry,
    )


async def _write_price_bar(cache: DataCacheOrFetch, key: str) -> None:
    """Write a PRICE_BAR entry through cache_or_fetch."""

    async def fetch_fn():
        return {"close": 150.0}

    await cache.cache_or_fetch(key=key, data_type=DataType.PRICE_BAR, fetch_fn=fetch_fn)


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


async def test_delayed_mode_applies_900_second_ttl(fake_redis, pg_repo) -> None:
    """Delayed mode (default) must produce a TTL ~900 seconds."""
    get_source_config = AsyncMock(
        return_value={"price_freshness_mode": PriceFreshnessMode.DELAYED}
    )
    selector = PriceModeSelector(get_source_config=get_source_config)

    ttl = await selector.get_price_ttl()
    assert ttl == 900, f"Expected 900 for delayed mode, got {ttl}"

    cache = _build_cache_with_ttl(fake_redis, pg_repo, price_ttl=ttl)
    key = build_cache_key(DataType.PRICE_BAR, "AAPL", {"mode": "delayed"})
    await _write_price_bar(cache, key)

    redis_ttl = await fake_redis.ttl(key)
    assert 895 <= redis_ttl <= 900, f"Expected Redis TTL ~900, got {redis_ttl}"


async def test_realtime_mode_applies_5_second_ttl(fake_redis, pg_repo) -> None:
    """Realtime mode must produce a TTL of 5 seconds."""
    get_source_config = AsyncMock(
        return_value={"price_freshness_mode": PriceFreshnessMode.REALTIME}
    )
    selector = PriceModeSelector(get_source_config=get_source_config)

    ttl = await selector.get_price_ttl()
    assert ttl == 5, f"Expected 5 for realtime mode, got {ttl}"

    cache = _build_cache_with_ttl(fake_redis, pg_repo, price_ttl=ttl)
    key = build_cache_key(DataType.PRICE_BAR, "MSFT", {"mode": "realtime"})
    await _write_price_bar(cache, key)

    redis_ttl = await fake_redis.ttl(key)
    assert 1 <= redis_ttl <= 5, f"Expected Redis TTL ~5, got {redis_ttl}"


async def test_mode_switch_requires_no_code_change(fake_redis, pg_repo) -> None:
    """Switching from delayed to realtime must work without module reload.

    Simulates an admin panel toggle: the mock is updated in-place to return
    a different mode; no service restart or code change is needed because
    PriceModeSelector reads config on every call.
    """
    config: dict[str, str] = {"price_freshness_mode": PriceFreshnessMode.DELAYED}

    async def dynamic_config(source_id: str) -> dict:
        return dict(config)  # returns current snapshot on each call

    selector = PriceModeSelector(get_source_config=dynamic_config)

    # First call: delayed mode → TTL 900
    ttl_delayed = await selector.get_price_ttl()
    assert ttl_delayed == 900

    key_delayed = build_cache_key(DataType.PRICE_BAR, "GOOGL", {"pass": "1"})
    cache_delayed = _build_cache_with_ttl(fake_redis, pg_repo, price_ttl=ttl_delayed)
    await _write_price_bar(cache_delayed, key_delayed)
    redis_ttl_delayed = await fake_redis.ttl(key_delayed)
    assert 895 <= redis_ttl_delayed <= 900

    # Toggle mode in-place — simulates admin panel flag change.
    config["price_freshness_mode"] = PriceFreshnessMode.REALTIME

    # Second call: realtime mode → TTL 5 (no code change, no reload)
    ttl_realtime = await selector.get_price_ttl()
    assert ttl_realtime == 5

    key_realtime = build_cache_key(DataType.PRICE_BAR, "GOOGL", {"pass": "2"})
    cache_realtime = _build_cache_with_ttl(fake_redis, pg_repo, price_ttl=ttl_realtime)
    await _write_price_bar(cache_realtime, key_realtime)
    redis_ttl_realtime = await fake_redis.ttl(key_realtime)
    assert 1 <= redis_ttl_realtime <= 5


async def test_unknown_mode_defaults_to_delayed(fake_redis, pg_repo) -> None:
    """An unrecognised price_freshness_mode value must default to 900 (safe default)."""
    get_source_config = AsyncMock(
        return_value={"price_freshness_mode": "turbo_quantum_speed"}
    )
    selector = PriceModeSelector(get_source_config=get_source_config)

    ttl = await selector.get_price_ttl()
    assert ttl == 900, (
        f"Unknown mode must default to delayed (900), got {ttl}"
    )

    # Must not raise during a full write cycle either.
    cache = _build_cache_with_ttl(fake_redis, pg_repo, price_ttl=ttl)
    key = build_cache_key(DataType.PRICE_BAR, "TSLA", {"mode": "unknown"})
    await _write_price_bar(cache, key)

    redis_ttl = await fake_redis.ttl(key)
    assert 895 <= redis_ttl <= 900
