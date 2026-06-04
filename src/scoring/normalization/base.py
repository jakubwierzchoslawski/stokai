"""Base Protocol for normalization strategies."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NormalizationStrategy(Protocol):
    """Normalize a raw value to [0, 100] range."""

    def normalize(self, value: float, **kwargs: float) -> float:
        """Return a score in [0.0, 100.0].

        Args:
            value: the raw computed value to normalize.
            **kwargs: strategy-specific parameters (e.g. mean, std, min_val, max_val).

        Returns:
            Normalized score in [0.0, 100.0].
        """
        ...


def invert_direction(score: float) -> float:
    """Invert a [0, 100] score for lower_better indicators."""
    return 100.0 - score
