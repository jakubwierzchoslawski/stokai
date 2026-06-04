"""
Unit tests for CacheService (mock Redis).

PLAN-F-030 TASK-006
"""
from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.admin.system.cache_service import CacheService, InvalidDataTypeError


# ── Mock Redis ────────────────────────────────────────────────────────────────


class _MockAsyncIter:
    """Async iterator that yields a fixed list of keys."""

    def __init__(self, keys: list[bytes]) -> None:
        self._keys = keys
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._keys):
            raise StopAsyncIteration
        key = self._keys[self._idx]
        self._idx += 1
        return key


def _make_redis(
    scan_keys: list[bytes] | None = None,
    memory_bytes: int = 1024,
) -> MagicMock:
    redis = MagicMock()
    keys = scan_keys or []

    redis.scan_iter = MagicMock(return_value=_MockAsyncIter(keys))
    redis.info = AsyncMock(return_value={"used_memory": memory_bytes})

    # Pipeline mock
    pipeline = MagicMock()
    pipeline.delete = MagicMock(return_value=pipeline)
    pipeline.execute = AsyncMock(return_value=[])
    redis.pipeline = MagicMock(return_value=pipeline)

    return redis


# ── force_refresh_cache ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestForceRefreshCache:
    async def test_force_refresh_price_bars_no_company_scans_all(self) -> None:
        """force_refresh('price_bars', None) uses pattern price_bar:*."""
        keys = [b"price_bar:uuid1:1h", b"price_bar:uuid2:1d"]
        redis = _make_redis(scan_keys=keys)
        service = CacheService(redis)

        deleted = await service.force_refresh_cache("price_bars", None)

        redis.scan_iter.assert_called_once_with("price_bar:*")
        assert deleted == 2

    async def test_force_refresh_price_bars_with_company_id_scoped_pattern(self) -> None:
        """force_refresh('price_bars', company_id) uses scoped pattern."""
        company_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        keys = [f"price_bar:{company_id}:1h".encode()]
        redis = _make_redis(scan_keys=keys)
        service = CacheService(redis)

        deleted = await service.force_refresh_cache("price_bars", company_id)

        redis.scan_iter.assert_called_once_with(f"price_bar:{company_id}:*")
        assert deleted == 1

    async def test_force_refresh_embeddings_correct_pattern(self) -> None:
        """force_refresh('embeddings', None) uses pattern embedding:*."""
        keys = [b"embedding:event1", b"embedding:event2"]
        redis = _make_redis(scan_keys=keys)
        service = CacheService(redis)

        deleted = await service.force_refresh_cache("embeddings", None)

        redis.scan_iter.assert_called_once_with("embedding:*")
        assert deleted == 2

    async def test_force_refresh_event_data_correct_pattern(self) -> None:
        """force_refresh('event_data', None) uses pattern event:*."""
        keys = [b"event:123"]
        redis = _make_redis(scan_keys=keys)
        service = CacheService(redis)

        deleted = await service.force_refresh_cache("event_data", None)

        redis.scan_iter.assert_called_once_with("event:*")
        assert deleted == 1

    async def test_force_refresh_invalid_type_raises(self) -> None:
        """force_refresh with unknown data_type raises InvalidDataTypeError."""
        redis = _make_redis()
        service = CacheService(redis)

        with pytest.raises(InvalidDataTypeError, match="invalid_type"):
            await service.force_refresh_cache("invalid_type", None)

    async def test_force_refresh_uses_pipeline_not_individual_deletes(self) -> None:
        """force_refresh uses SCAN+pipeline DEL, not individual redis.delete calls."""
        keys = [b"price_bar:a", b"price_bar:b"]
        redis = _make_redis(scan_keys=keys)
        service = CacheService(redis)

        await service.force_refresh_cache("price_bars", None)

        # pipeline.delete should be called per key
        pipeline = redis.pipeline.return_value
        assert pipeline.delete.call_count == 2
        pipeline.execute.assert_called_once()


# ── get_cache_stats ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetCacheStats:
    async def test_get_cache_stats_non_negative_counts(self) -> None:
        """get_cache_stats returns non-negative key counts."""
        redis = _make_redis(scan_keys=[], memory_bytes=2048)
        service = CacheService(redis)

        stats = await service.get_cache_stats()

        assert stats.price_bars_count >= 0
        assert stats.embeddings_count >= 0
        assert stats.event_data_count >= 0

    async def test_get_cache_stats_total_redis_memory_bytes_positive(self) -> None:
        """get_cache_stats.total_redis_memory_bytes > 0 when Redis has memory."""
        redis = _make_redis(scan_keys=[], memory_bytes=4096)
        service = CacheService(redis)

        stats = await service.get_cache_stats()

        assert stats.total_redis_memory_bytes > 0

    async def test_get_cache_stats_counts_keys_by_pattern(self) -> None:
        """get_cache_stats calls scan_iter for each pattern."""
        redis = MagicMock()
        call_count = 0

        def scan_iter_side_effect(pattern):
            nonlocal call_count
            call_count += 1
            return _MockAsyncIter([])

        redis.scan_iter = MagicMock(side_effect=scan_iter_side_effect)
        redis.info = AsyncMock(return_value={"used_memory": 1024})

        service = CacheService(redis)
        stats = await service.get_cache_stats()

        # Should call scan_iter 3 times: price_bar:*, embedding:*, event:*
        assert call_count == 3
