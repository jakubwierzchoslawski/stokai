"""Min-max normalization strategy."""
from __future__ import annotations


class MinMaxNormalizer:
    """Normalizes a value within a [min_val, max_val] range to [0, 100].

    Formula: score = (value - min_val) / (max_val - min_val) * 100.
    Values outside the range are clipped.

    Args:
        direction: "higher_better" (default) or "lower_better".
    """

    def __init__(self, direction: str = "higher_better") -> None:
        self._direction = direction

    def normalize(self, value: float, **kwargs: float) -> float:
        """Compute min-max normalized score.

        Keyword args:
            min_val (float): the lower bound (maps to 0.0 or 100.0 if lower_better).
            max_val (float): the upper bound (maps to 100.0 or 0.0 if lower_better).

        Returns:
            Score in [0.0, 100.0].

        Raises:
            ValueError: if min_val >= max_val.
        """
        min_val = float(kwargs.get("min_val", 0.0))
        max_val = float(kwargs.get("max_val", 100.0))

        if min_val >= max_val:
            raise ValueError(
                f"min_val ({min_val}) must be strictly less than max_val ({max_val})"
            )

        score = (value - min_val) / (max_val - min_val) * 100.0

        # Clip to [0, 100]
        score = max(0.0, min(100.0, score))

        if self._direction == "lower_better":
            score = 100.0 - score

        return score
