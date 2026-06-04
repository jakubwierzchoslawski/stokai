"""Z-score normalization strategy — clips result to [0, 100]."""
from __future__ import annotations


class ZScoreNormalizer:
    """Normalizes using z-score, then maps to [0, 100].

    Mapping: z-score of 0 → 50, z=+2 → ~95, z=-2 → ~5.
    Formula: score = 50 + z * 25, clipped to [0, 100].

    Args:
        direction: "higher_better" (default) or "lower_better".
    """

    def __init__(self, direction: str = "higher_better") -> None:
        self._direction = direction

    def normalize(self, value: float, **kwargs: float) -> float:
        """Compute z-score normalized score.

        Keyword args:
            mean (float): population mean.
            std (float): population standard deviation.

        Returns:
            Score in [0.0, 100.0].
        """
        mean = float(kwargs.get("mean", 0.0))
        std = float(kwargs.get("std", 1.0))

        if std == 0.0:
            score = 50.0
        else:
            z = (value - mean) / std
            score = 50.0 + z * 25.0

        # Clip to [0, 100]
        score = max(0.0, min(100.0, score))

        if self._direction == "lower_better":
            score = 100.0 - score

        return score
