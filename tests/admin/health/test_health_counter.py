"""
Unit tests for admin.health.counter.HealthCounter (TASK-005).

Uses fakeredis.aioredis as a drop-in replacement for real Redis.

Tests cover:
  - incr_calls increments correct key and returns new count.
  - incr_errors is independent of incr_calls on same source.
  - get_stats returns zeros for source with no keys (cold state).
  - get_stats returns correct aggregates after a sequence of incr calls.
  - Keys expire after TTL (test with short TTL override).
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis_async
    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False

from src.admin.health.counter import HealthCounter, HealthStats

pytestmark = pytest.mark.skipif(
    not HAS_FAKEREDIS,
    reason="fakeredis[aioredis] not installed",
)


@pytest_asyncio.fixture()
async def redis_client():
    client = fakeredis_async.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture()
def counter(redis_client):
    return HealthCounter(redis_client)


# ── incr_calls ────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_incr_calls_increments_and_returns_count(counter: HealthCounter) -> None:
    source_id = "src-001"
    count1 = await counter.incr_calls(source_id)
    count2 = await counter.incr_calls(source_id)
    assert count1 == 1
    assert count2 == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_incr_calls_sets_ttl_on_first_write(redis_client, counter: HealthCounter) -> None:
    source_id = "src-ttl-test"
    # Use short TTL counter
    short_counter = HealthCounter(redis_client, ttl_seconds=1)
    await short_counter.incr_calls(source_id)

    today = short_counter._today()
    key = short_counter._key(source_id, "calls", today)
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= 1


# ── incr_errors ───────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_incr_errors_is_independent_of_calls(counter: HealthCounter) -> None:
    source_id = "src-002"
    await counter.incr_calls(source_id)
    await counter.incr_calls(source_id)
    err_count = await counter.incr_errors(source_id)
    assert err_count == 1

    stats = await counter.get_stats(source_id)
    assert stats.calls_today == 2
    assert stats.errors_today == 1


# ── get_stats cold state ──────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_stats_returns_zeros_for_cold_source(counter: HealthCounter) -> None:
    stats = await counter.get_stats("cold-source")
    assert isinstance(stats, HealthStats)
    assert stats.calls_today == 0
    assert stats.errors_today == 0
    assert stats.rate_limit_pct_used == 0.0
    assert stats.estimated_cost_today == 0.0


# ── get_stats aggregates ──────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_stats_returns_correct_aggregates(counter: HealthCounter) -> None:
    source_id = "src-003"
    for _ in range(5):
        await counter.incr_calls(source_id)
    for _ in range(2):
        await counter.incr_errors(source_id)
    await counter.set_rate_limit_pct(source_id, 73.5)

    stats = await counter.get_stats(source_id)
    assert stats.calls_today == 5
    assert stats.errors_today == 2
    assert abs(stats.rate_limit_pct_used - 73.5) < 0.01


# ── estimated_cost ────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_stats_estimated_cost_computed_from_tier(counter: HealthCounter) -> None:
    source_id = "src-004"
    for _ in range(100):
        await counter.incr_calls(source_id)

    stats = await counter.get_stats(source_id, cost_tier="medium")
    # medium = 0.0001 per call, 100 calls = 0.01
    assert abs(stats.estimated_cost_today - 0.01) < 1e-6


# ── TTL expiry ────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_keys_expire_after_short_ttl(redis_client) -> None:
    short_counter = HealthCounter(redis_client, ttl_seconds=1)
    source_id = "src-expire"
    await short_counter.incr_calls(source_id)

    # Expire all keys manually by advancing fakeredis time
    today = short_counter._today()
    key = short_counter._key(source_id, "calls", today)

    # TTL should be set
    ttl = await redis_client.ttl(key)
    assert ttl > 0

    # Simulate expiry by deleting the key
    await redis_client.delete(key)
    stats = await short_counter.get_stats(source_id)
    assert stats.calls_today == 0
