"""TDD tests for ScoreCacheInvalidator — written before implementation.

Verifies event-driven invalidation semantics:
- company_score entries are deleted from both Redis and PG on invalidation.
- No time-based TTL is set when a score is stored.
- Scores retain their value until an explicit invalidation event fires.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis
import msgpack
from unittest.mock import AsyncMock, MagicMock, call

from ingestion.redis_cache import RedisCacheLayer
from ingestion.invalidation import ScoreCacheInvalidator
from ingestion.cache_or_fetch import DataCacheOrFetch
from ingestion.ttl_policy import DataType, DEFAULT_TTL_REGISTRY


def _pack(value: object) -> bytes:
    return msgpack.packb(value, use_bin_type=True)


def _score_key(company_id: str) -> str:
    return f"company_score:{company_id}:latest"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.fixture
def mock_redis_layer():
    layer = MagicMock()
    layer.delete = AsyncMock()
    layer.set = AsyncMock()
    layer.get = AsyncMock(return_value=None)
    return layer


@pytest.fixture
def mock_pg_repo():
    repo = MagicMock()
    repo.delete = AsyncMock()
    repo.set = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    return repo


# ---------------------------------------------------------------------------
# test_invalidate_company_score_deletes_redis_and_pg_entries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalidate_company_score_deletes_redis_and_pg_entries(
    mock_redis_layer, mock_pg_repo
):
    """Both Redis and PG must be deleted for the correct cache key."""
    invalidator = ScoreCacheInvalidator(
        redis_layer=mock_redis_layer, pg_repo=mock_pg_repo
    )

    await invalidator.invalidate_company_score("AAPL")

    expected_key = _score_key("AAPL")
    mock_redis_layer.delete.assert_called_once_with(expected_key)
    mock_pg_repo.delete.assert_called_once_with(expected_key)


# ---------------------------------------------------------------------------
# test_invalidate_scores_for_event_deletes_all_exposed_companies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalidate_scores_for_event_deletes_all_exposed_companies(
    mock_redis_layer, mock_pg_repo
):
    """Three company_ids → three Redis.delete and three PG.delete calls."""
    invalidator = ScoreCacheInvalidator(
        redis_layer=mock_redis_layer, pg_repo=mock_pg_repo
    )
    company_ids = ["AAPL", "MSFT", "GOOGL"]

    await invalidator.invalidate_scores_for_event(
        event_id="evt-001", company_ids=company_ids
    )

    assert mock_redis_layer.delete.call_count == 3
    assert mock_pg_repo.delete.call_count == 3

    expected_keys = [_score_key(cid) for cid in company_ids]
    for key in expected_keys:
        mock_redis_layer.delete.assert_any_call(key)
        mock_pg_repo.delete.assert_any_call(key)


# ---------------------------------------------------------------------------
# test_score_is_not_invalidated_by_time
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_is_not_invalidated_by_time(fake_redis, mock_pg_repo):
    """COMPANY_SCORE must be stored with ttl_seconds=None (no time-based expiry)."""
    real_redis_layer = RedisCacheLayer(fake_redis)
    cache = DataCacheOrFetch(
        redis_layer=real_redis_layer,
        pg_repo=mock_pg_repo,
        ttl_registry=DEFAULT_TTL_REGISTRY,
    )

    fetch_fn = AsyncMock(return_value={"score": 7.5})
    key = _score_key("AAPL")

    await cache.cache_or_fetch(
        key=key,
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )

    # Redis key must have NO TTL (no time-based invalidation)
    ttl = await fake_redis.ttl(key)
    assert ttl == -1, (
        f"company_score must have no Redis TTL; got {ttl}. "
        "Scores are only invalidated by events, not time."
    )

    # PG set must have been called with ttl_seconds=None
    mock_pg_repo.set.assert_called_once()
    args = mock_pg_repo.set.call_args.args
    assert args[3] is None, "PG set must receive ttl_seconds=None for company_score"


# ---------------------------------------------------------------------------
# test_score_retains_value_between_events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_retains_value_between_events(fake_redis, mock_pg_repo):
    """Score stored in Redis must be returned unchanged on second read without fetch_fn."""
    real_redis_layer = RedisCacheLayer(fake_redis)
    cache = DataCacheOrFetch(
        redis_layer=real_redis_layer,
        pg_repo=mock_pg_repo,
        ttl_registry=DEFAULT_TTL_REGISTRY,
    )

    original_score = {"score": 8.9, "computed_at": "2026-06-03T10:00:00Z"}
    fetch_fn = AsyncMock(return_value=original_score)
    key = _score_key("MSFT")

    # First call — populates cache
    result1 = await cache.cache_or_fetch(
        key=key,
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn,
    )
    assert result1 == original_score

    # Second call — no event fired, score must be returned from cache
    fetch_fn2 = AsyncMock(return_value={"score": 0.0, "computed_at": "WRONG"})
    result2 = await cache.cache_or_fetch(
        key=key,
        data_type=DataType.COMPANY_SCORE,
        fetch_fn=fetch_fn2,
    )

    assert result2 == original_score, "Score must retain its value between events"
    fetch_fn2.assert_not_called()
