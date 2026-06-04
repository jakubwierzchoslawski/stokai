"""Tests for normalization strategies (TDD — written before implementation)."""
from __future__ import annotations

import pytest

from src.scoring.normalization.percentile import PercentileNormalizer
from src.scoring.normalization.z_score import ZScoreNormalizer
from src.scoring.normalization.min_max import MinMaxNormalizer


class TestPercentileNormalizer:
    def test_percentile_middle_value(self):
        """PercentileNormalizer: 75.0 against [50,60,70,80,90] → 2/5 * 100 = 40.0"""
        n = PercentileNormalizer()
        result = n.normalize(75.0, peer_values=[50.0, 60.0, 70.0, 80.0, 90.0])
        assert result == pytest.approx(40.0)

    def test_percentile_highest_value(self):
        """Value higher than all peers → 100.0"""
        n = PercentileNormalizer()
        result = n.normalize(100.0, peer_values=[10.0, 20.0, 30.0])
        assert result == pytest.approx(100.0)

    def test_percentile_lowest_value(self):
        """Value lower than all peers → 0.0"""
        n = PercentileNormalizer()
        result = n.normalize(0.0, peer_values=[10.0, 20.0, 30.0])
        assert result == pytest.approx(0.0)

    def test_percentile_lower_better_inverts(self):
        """With direction=lower_better, inversion: value at 0th percentile → 100."""
        n = PercentileNormalizer(direction="lower_better")
        # value=0, all peers are higher → 0th percentile → inverted = 100
        result = n.normalize(0.0, peer_values=[10.0, 20.0, 30.0])
        assert result == pytest.approx(100.0)

    def test_percentile_lower_better_top_value(self):
        """With direction=lower_better, value above all peers → 0 (was 100, now inverted)."""
        n = PercentileNormalizer(direction="lower_better")
        result = n.normalize(100.0, peer_values=[10.0, 20.0, 30.0])
        assert result == pytest.approx(0.0)

    def test_percentile_no_peers_returns_50(self):
        """No peer values → returns 50.0 by convention."""
        n = PercentileNormalizer()
        result = n.normalize(50.0, peer_values=[])
        assert result == pytest.approx(50.0)


class TestZScoreNormalizer:
    def test_z_score_one_std_above_mean(self):
        """value=110, mean=100, std=10 → z=1.0 → score=50+25=75.0"""
        n = ZScoreNormalizer()
        result = n.normalize(110.0, mean=100.0, std=10.0)
        assert result == pytest.approx(75.0)

    def test_z_score_clipped_upper(self):
        """Very high z-score clipped to 100.0"""
        n = ZScoreNormalizer()
        result = n.normalize(1000.0, mean=100.0, std=10.0)
        assert result == pytest.approx(100.0)

    def test_z_score_clipped_lower(self):
        """Very low z-score clipped to 0.0"""
        n = ZScoreNormalizer()
        result = n.normalize(-1000.0, mean=100.0, std=10.0)
        assert result == pytest.approx(0.0)

    def test_z_score_at_mean(self):
        """value == mean → z=0 → score=50.0"""
        n = ZScoreNormalizer()
        result = n.normalize(100.0, mean=100.0, std=10.0)
        assert result == pytest.approx(50.0)

    def test_z_score_lower_better(self):
        """With lower_better, value at mean → 50.0 (inverted from 50.0)"""
        n = ZScoreNormalizer(direction="lower_better")
        result = n.normalize(100.0, mean=100.0, std=10.0)
        assert result == pytest.approx(50.0)

    def test_z_score_lower_better_high_value(self):
        """With lower_better, very high value → 0.0 (inverted from 100.0)"""
        n = ZScoreNormalizer(direction="lower_better")
        result = n.normalize(1000.0, mean=100.0, std=10.0)
        assert result == pytest.approx(0.0)

    def test_z_score_zero_std(self):
        """std=0 → returns 50.0 (no spread)"""
        n = ZScoreNormalizer()
        result = n.normalize(100.0, mean=100.0, std=0.0)
        assert result == pytest.approx(50.0)


class TestMinMaxNormalizer:
    def test_min_max_middle(self):
        """value=150, min=100, max=200 → (150-100)/(200-100)*100 = 50.0"""
        n = MinMaxNormalizer()
        result = n.normalize(150.0, min_val=100.0, max_val=200.0)
        assert result == pytest.approx(50.0)

    def test_min_max_at_min(self):
        """value == min_val → 0.0"""
        n = MinMaxNormalizer()
        result = n.normalize(100.0, min_val=100.0, max_val=200.0)
        assert result == pytest.approx(0.0)

    def test_min_max_at_max(self):
        """value == max_val → 100.0"""
        n = MinMaxNormalizer()
        result = n.normalize(200.0, min_val=100.0, max_val=200.0)
        assert result == pytest.approx(100.0)

    def test_min_max_below_min_clipped(self):
        """value < min_val → clipped to 0.0"""
        n = MinMaxNormalizer()
        result = n.normalize(50.0, min_val=100.0, max_val=200.0)
        assert result == pytest.approx(0.0)

    def test_min_max_above_max_clipped(self):
        """value > max_val → clipped to 100.0"""
        n = MinMaxNormalizer()
        result = n.normalize(250.0, min_val=100.0, max_val=200.0)
        assert result == pytest.approx(100.0)

    def test_min_max_lower_better(self):
        """With lower_better: value at min → 100.0 (inverted)"""
        n = MinMaxNormalizer(direction="lower_better")
        result = n.normalize(100.0, min_val=100.0, max_val=200.0)
        assert result == pytest.approx(100.0)

    def test_min_max_lower_better_at_max(self):
        """With lower_better: value at max → 0.0 (inverted)"""
        n = MinMaxNormalizer(direction="lower_better")
        result = n.normalize(200.0, min_val=100.0, max_val=200.0)
        assert result == pytest.approx(0.0)

    def test_min_max_invalid_range_raises(self):
        """min_val >= max_val → ValueError"""
        n = MinMaxNormalizer()
        with pytest.raises(ValueError):
            n.normalize(100.0, min_val=200.0, max_val=100.0)
