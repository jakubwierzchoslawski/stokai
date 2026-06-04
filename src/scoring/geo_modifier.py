"""Geo-modifier: applies geopolitical event exposure to base scores.

Formula:
    exposure_fraction = sum(geo_revenue.get(region, 0) for region in event_regions)
    magnitude = exposure_fraction * (event_intensity / 5) * event_sentiment * geo_weight
    geo_adjusted = clamp(base_score * (1 + magnitude), 0, 100)
"""
from __future__ import annotations


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class GeoModifier:
    """Applies geopolitical event risk/opportunity adjustment to a base score.

    Pure computation — no I/O, no DB access.
    """

    def apply(
        self,
        base_score: float,
        geo_weight: float,
        geo_revenue: dict[str, float] | None = None,
        event_regions: list[str] | None = None,
        event_intensity: int = 0,
        event_sentiment: float = 0.0,
    ) -> float:
        """Return the geo-adjusted score.

        Args:
            base_score: normalized score before geo adjustment [0, 100].
            geo_weight: indicator-level geo weight [0, 1]. 0 disables adjustment.
            geo_revenue: mapping of ISO country code → fraction of revenue [0, 1].
            event_regions: list of region codes affected by the event.
            event_intensity: event intensity [1, 5].
            event_sentiment: signed sentiment [-1, 1]; negative = bearish, positive = bullish.

        Returns:
            Geo-adjusted score in [0, 100].
        """
        if geo_weight == 0.0 or not event_regions or not geo_revenue:
            return _clamp(base_score)

        exposure_fraction = sum(
            geo_revenue.get(region, 0.0) for region in event_regions
        )

        if exposure_fraction == 0.0:
            return _clamp(base_score)

        magnitude = exposure_fraction * (event_intensity / 5.0) * event_sentiment * geo_weight
        geo_adjusted = base_score * (1.0 + magnitude)
        return _clamp(geo_adjusted)
