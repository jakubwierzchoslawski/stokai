"""TDD tests for ranking DSL operators (PLAN-F-003 TASK-006).

Tests written before implementation.
AC-002: DSL indicator evaluates correctly.
"""
from __future__ import annotations

import pytest

from src.scoring.exceptions import DslEvalError


class TestRankingOperators:
    """Unit tests for ranking operator functions."""

    @pytest.fixture
    def ranking(self):
        from src.scoring.dsl.operators.ranking import RankingOps
        return RankingOps

    def test_rank_sector_known_dataset(self, ranking):
        """value=3.0 among [1, 2, 3, 4, 5] → rank 3 (1-based ascending)."""
        result = ranking.rank_sector(3.0, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert result == pytest.approx(3.0)

    def test_rank_sector_smallest_value(self, ranking):
        """Smallest value → rank 1."""
        result = ranking.rank_sector(1.0, [1.0, 2.0, 3.0])
        assert result == pytest.approx(1.0)

    def test_rank_sector_largest_value(self, ranking):
        """Largest value → rank N."""
        result = ranking.rank_sector(5.0, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert result == pytest.approx(5.0)

    def test_rank_sector_value_not_in_peers(self, ranking):
        """Value 2.5 among [1, 2, 3, 4] → rank 3 (between 2 and 3, counts as above 2)."""
        # 2.5 > 1, 2.5 > 2, 2.5 < 3, so rank is 3
        result = ranking.rank_sector(2.5, [1.0, 2.0, 3.0, 4.0])
        assert result == pytest.approx(3.0)

    def test_rank_sector_empty_peers_raises(self, ranking):
        """Empty peer list raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ranking.rank_sector(3.0, [])

    def test_percentile_known_dataset(self, ranking):
        """Value at median of 0..100 → 50th percentile."""
        peers = list(range(0, 101))  # 0, 1, ..., 100
        result = ranking.percentile(50.0, [float(x) for x in peers])
        assert result == pytest.approx(50.0, abs=1.0)

    def test_percentile_min_value(self, ranking):
        """Minimum value → approximately 0th percentile."""
        result = ranking.percentile(0.0, [0.0, 25.0, 50.0, 75.0, 100.0])
        assert result == pytest.approx(0.0)

    def test_percentile_max_value(self, ranking):
        """Maximum value → 100th percentile."""
        result = ranking.percentile(100.0, [0.0, 25.0, 50.0, 75.0, 100.0])
        assert result == pytest.approx(100.0)

    def test_percentile_result_in_range(self, ranking):
        """Result is always in [0.0, 100.0]."""
        result = ranking.percentile(3.0, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert 0.0 <= result <= 100.0

    def test_percentile_empty_peers_raises(self, ranking):
        """Empty peer list raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ranking.percentile(5.0, [])
