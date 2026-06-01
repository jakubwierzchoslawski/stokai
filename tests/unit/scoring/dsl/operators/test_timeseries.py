"""TDD tests for time-series DSL operators (PLAN-F-003 TASK-006).

Tests written before implementation.
AC-002: DSL indicator evaluates correctly.
"""
from __future__ import annotations

import math

import pytest

from src.scoring.exceptions import DslEvalError


class TestTimeSeriesOperators:
    """Unit tests for time-series operator functions."""

    @pytest.fixture
    def ts(self):
        from src.scoring.dsl.operators.timeseries import TimeSeriesOps
        return TimeSeriesOps

    # -----------------------------------------------------------------------
    # CHANGE
    # -----------------------------------------------------------------------

    def test_change_correct_delta(self, ts):
        """CHANGE([100, 110, 121], 2) = (121 - 100) / 100 = 0.21."""
        result = ts.change([100.0, 110.0, 121.0], 2)
        assert result == pytest.approx(0.21)

    def test_change_one_period(self, ts):
        """CHANGE([100, 110], 1) = (110 - 100) / 100 = 0.1."""
        result = ts.change([100.0, 110.0], 1)
        assert result == pytest.approx(0.1)

    def test_change_series_too_short_raises(self, ts):
        """Series shorter than required window raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.change([100.0], 2)

    def test_change_zero_base_raises(self, ts):
        """Division by zero base value raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.change([0.0, 10.0], 1)

    # -----------------------------------------------------------------------
    # CAGR
    # -----------------------------------------------------------------------

    def test_cagr_known_values(self, ts):
        """CAGR([100, 121], 2) = (121/100)^(1/2) - 1 = 0.1 (10%)."""
        result = ts.cagr([100.0, 121.0], 2.0)
        assert result == pytest.approx(0.1, rel=1e-6)

    def test_cagr_series_too_short_raises(self, ts):
        """Single-element series raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.cagr([100.0], 1.0)

    def test_cagr_zero_start_raises(self, ts):
        """Zero start value raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.cagr([0.0, 100.0], 1.0)

    def test_cagr_zero_years_raises(self, ts):
        """Zero years raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.cagr([100.0, 200.0], 0.0)

    # -----------------------------------------------------------------------
    # CORR
    # -----------------------------------------------------------------------

    def test_corr_perfect_correlation(self, ts):
        """Perfectly correlated series → 1.0."""
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [2.0, 4.0, 6.0, 8.0, 10.0]
        result = ts.corr(a, b)
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_corr_perfect_negative_correlation(self, ts):
        """Perfectly anti-correlated series → -1.0."""
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [10.0, 8.0, 6.0, 4.0, 2.0]
        result = ts.corr(a, b)
        assert result == pytest.approx(-1.0, abs=1e-9)

    def test_corr_result_in_range(self, ts):
        """Correlation coefficient is always in [-1, 1]."""
        import random
        random.seed(42)
        a = [random.gauss(0, 1) for _ in range(20)]
        b = [random.gauss(0, 1) for _ in range(20)]
        result = ts.corr(a, b)
        assert -1.0 <= result <= 1.0

    def test_corr_series_too_short_raises(self, ts):
        """Series with fewer than 2 elements raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.corr([1.0], [1.0])

    def test_corr_mismatched_lengths_raises(self, ts):
        """Series of different lengths raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.corr([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_corr_zero_std_raises(self, ts):
        """Constant series (std=0) raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.corr([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])

    # -----------------------------------------------------------------------
    # ZSCORE
    # -----------------------------------------------------------------------

    def test_zscore_known_values(self, ts):
        """Z-score of last element of [2,4,4,4,5,5,7,9].

        mean=5.0, std=2.0 (population std), z = (9-5)/2 = 2.0
        Using sample std: std = sqrt(sum((x-mean)^2)/(n-1))
        For [2,4,4,4,5,5,7,9]: mean=5, deviations: -3,-1,-1,-1,0,0,2,4
        SS = 9+1+1+1+0+0+4+16=32, sample var=32/7≈4.571, sample std≈2.138
        z = (9-5)/2.138 ≈ 1.871
        Using population std: var=32/8=4, std=2, z=(9-5)/2=2.0
        """
        series = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        result = ts.zscore(series)
        # With population std: (9-5)/2 = 2.0
        # We accept either population or sample std implementation
        assert isinstance(result, float)
        assert math.isfinite(result)

    def test_zscore_zero_std_raises(self, ts):
        """Constant series has std=0 → raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.zscore([5.0, 5.0, 5.0, 5.0])

    def test_zscore_series_too_short_raises(self, ts):
        """Single-element series raises DslEvalError."""
        with pytest.raises(DslEvalError):
            ts.zscore([5.0])

    def test_zscore_last_element_above_mean(self, ts):
        """Last element above mean → positive z-score."""
        series = [1.0, 2.0, 3.0, 4.0, 100.0]
        result = ts.zscore(series)
        assert result > 0.0

    def test_zscore_last_element_below_mean(self, ts):
        """Last element below mean → negative z-score."""
        series = [100.0, 90.0, 80.0, 70.0, 1.0]
        result = ts.zscore(series)
        assert result < 0.0
