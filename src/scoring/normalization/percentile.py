"""Percentile-rank normalization strategy."""
from __future__ import annotations


class PercentileNormalizer:
    """Converts a raw value to its percentile rank within a peer set.

    Score = (number of peer values strictly below *value*) / len(peer_values) * 100.

    Args:
        direction: "higher_better" (default) or "lower_better".
    """

    def __init__(self, direction: str = "higher_better") -> None:
        self._direction = direction

    def normalize(self, value: float, **kwargs: float) -> float:
        """Compute percentile rank.

        Keyword args:
            peer_values: list of float peer values (passed as positional list via
                the ``peer_values`` keyword). If not supplied, returns 50.0.

        Returns:
            Score in [0.0, 100.0].
        """
        peer_values_raw = kwargs.get("peer_values", [])
        # Accept list passed as keyword arg (type: ignore because Protocol uses **float)
        if not peer_values_raw:
            return 50.0

        # peer_values may be passed as a list in the kwargs dict
        if hasattr(peer_values_raw, "__iter__"):
            peer_list = list(peer_values_raw)
        else:
            peer_list = [float(peer_values_raw)]

        if len(peer_list) == 0:
            return 50.0

        below = sum(1 for p in peer_list if p < value)
        score = (below / len(peer_list)) * 100.0

        # Clamp to [0, 100]
        score = max(0.0, min(100.0, score))

        if self._direction == "lower_better":
            score = 100.0 - score

        return score
