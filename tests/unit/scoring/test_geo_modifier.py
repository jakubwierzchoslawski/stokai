"""Tests for GeoModifier (TDD — written before implementation)."""
from __future__ import annotations

import pytest

from src.scoring.geo_modifier import GeoModifier


class TestGeoModifier:
    def test_zero_geo_weight_no_adjustment(self):
        """geo_weight=0.0 → geo_adjusted == base_score (clamped)."""
        m = GeoModifier()
        result = m.apply(
            base_score=80.0,
            geo_weight=0.0,
            geo_revenue={"US": 0.6, "CN": 0.4},
            event_regions=["CN"],
            event_intensity=4,
            event_sentiment=-1.0,
        )
        assert result == pytest.approx(80.0)

    def test_geo_modifier_applied(self):
        """apply with exposure → result between 0 and 100."""
        m = GeoModifier()
        result = m.apply(
            base_score=80.0,
            geo_weight=0.3,
            geo_revenue={"US": 0.6, "CN": 0.4},
            event_regions=["CN"],
            event_intensity=4,
            event_sentiment=-1.0,
        )
        assert 0.0 <= result <= 100.0

    def test_result_clamped_above_100(self):
        """Result is clamped to [0, 100] — never exceeds 100."""
        m = GeoModifier()
        result = m.apply(
            base_score=99.0,
            geo_weight=1.0,
            geo_revenue={"US": 1.0},
            event_regions=["US"],
            event_intensity=5,
            event_sentiment=1.0,  # highly positive
        )
        assert result <= 100.0

    def test_result_clamped_below_0(self):
        """Result is clamped to [0, 100] — never below 0."""
        m = GeoModifier()
        result = m.apply(
            base_score=1.0,
            geo_weight=1.0,
            geo_revenue={"US": 1.0},
            event_regions=["US"],
            event_intensity=5,
            event_sentiment=-1.0,  # highly negative
        )
        assert result >= 0.0

    def test_no_overlap_regions_no_adjustment(self):
        """event_regions not overlapping geo_revenue → geo_adjusted == base_score."""
        m = GeoModifier()
        result = m.apply(
            base_score=60.0,
            geo_weight=0.5,
            geo_revenue={"US": 0.8, "DE": 0.2},
            event_regions=["CN", "JP"],
            event_intensity=3,
            event_sentiment=-0.5,
        )
        assert result == pytest.approx(60.0)

    def test_no_event_regions_no_adjustment(self):
        """Empty event_regions → no adjustment."""
        m = GeoModifier()
        result = m.apply(
            base_score=70.0,
            geo_weight=0.5,
            geo_revenue={"US": 1.0},
            event_regions=[],
            event_intensity=3,
            event_sentiment=-0.5,
        )
        assert result == pytest.approx(70.0)

    def test_no_geo_revenue_no_adjustment(self):
        """None geo_revenue → no adjustment."""
        m = GeoModifier()
        result = m.apply(
            base_score=70.0,
            geo_weight=0.5,
            geo_revenue=None,
            event_regions=["US"],
            event_intensity=3,
            event_sentiment=-0.5,
        )
        assert result == pytest.approx(70.0)

    def test_positive_sentiment_increases_score(self):
        """Positive sentiment and overlap → result > base_score."""
        m = GeoModifier()
        result = m.apply(
            base_score=50.0,
            geo_weight=0.5,
            geo_revenue={"US": 1.0},
            event_regions=["US"],
            event_intensity=5,
            event_sentiment=1.0,
        )
        assert result > 50.0

    def test_negative_sentiment_decreases_score(self):
        """Negative sentiment and overlap → result < base_score."""
        m = GeoModifier()
        result = m.apply(
            base_score=50.0,
            geo_weight=0.5,
            geo_revenue={"US": 1.0},
            event_regions=["US"],
            event_intensity=5,
            event_sentiment=-1.0,
        )
        assert result < 50.0
