"""Tests for BenchmarkEngine (TDD — written before implementation)."""
from __future__ import annotations

import math
import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from src.scoring.benchmark_engine import BenchmarkEngine, BenchmarkStats, InsufficientPeerDataError

INDICATOR_ID = UUID("00000000-0000-0000-0000-000000000010")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_score_repo(values: list[float]):
    repo = AsyncMock()
    repo.get_peer_scores = AsyncMock(return_value=values)
    return repo


def _make_indicator_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=object())
    return repo


class TestGetPeerValues:
    @pytest.mark.asyncio
    async def test_returns_list_of_floats(self):
        values = [10.0, 20.0, 30.0, 40.0]
        engine = BenchmarkEngine(_make_score_repo(values), _make_indicator_repo())
        result = await engine.get_peer_values(INDICATOR_ID, "SP500", TENANT_ID)
        assert result == values

    @pytest.mark.asyncio
    async def test_empty_peer_list_raises(self):
        engine = BenchmarkEngine(_make_score_repo([]), _make_indicator_repo())
        with pytest.raises(InsufficientPeerDataError):
            await engine.get_peer_values(INDICATOR_ID, "SP500", TENANT_ID)

    @pytest.mark.asyncio
    async def test_single_element_raises(self):
        engine = BenchmarkEngine(_make_score_repo([42.0]), _make_indicator_repo())
        with pytest.raises(InsufficientPeerDataError):
            await engine.get_peer_values(INDICATOR_ID, "SP500", TENANT_ID)


class TestComputeBenchmarkStats:
    def test_basic_stats(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        engine = BenchmarkEngine(_make_score_repo(values), _make_indicator_repo())
        stats = engine.compute_benchmark_stats(values)
        assert isinstance(stats, BenchmarkStats)
        assert stats.mean == pytest.approx(30.0)
        assert stats.min == pytest.approx(10.0)
        assert stats.max == pytest.approx(50.0)

    def test_std_computed(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        engine = BenchmarkEngine(_make_score_repo(values), _make_indicator_repo())
        stats = engine.compute_benchmark_stats(values)
        expected_variance = sum((x - 30.0) ** 2 for x in values) / len(values)
        assert stats.std == pytest.approx(math.sqrt(expected_variance))

    def test_percentiles(self):
        values = list(range(1, 101))  # 1..100
        engine = BenchmarkEngine(_make_score_repo(values), _make_indicator_repo())
        stats = engine.compute_benchmark_stats([float(v) for v in values])
        assert stats.p50 == pytest.approx(50.5, abs=1.0)

    def test_empty_raises(self):
        engine = BenchmarkEngine(_make_score_repo([]), _make_indicator_repo())
        with pytest.raises(InsufficientPeerDataError):
            engine.compute_benchmark_stats([])

    def test_one_element_raises(self):
        engine = BenchmarkEngine(_make_score_repo([1.0]), _make_indicator_repo())
        with pytest.raises(InsufficientPeerDataError):
            engine.compute_benchmark_stats([1.0])
