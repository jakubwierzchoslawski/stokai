"""Time-series operator implementations for the scoring DSL (PLAN-F-003 TASK-006).

Provides TimeSeriesOps — pure static methods for CHANGE, CAGR, CORR, ZSCORE.

All methods are pure functions: no I/O, no DB, no mutable state.
Insufficient data or degenerate inputs raise ``DslEvalError``.
"""
from __future__ import annotations

import math
import statistics

from src.scoring.exceptions import DslEvalError


class TimeSeriesOps:
    """Pure static time-series operator registry."""

    @staticmethod
    def change(series: list[float], periods: int) -> float:
        """Return the relative change over *periods* periods.

        Formula: ``(series[-1] - series[-periods]) / series[-periods]``

        Parameters
        ----------
        series:
            Time-ordered price/value series (oldest first).
        periods:
            Number of periods back to compute the change from.

        Raises
        ------
        DslEvalError
            When the series is shorter than ``periods + 1`` elements, or when
            the base value is zero.
        """
        if len(series) <= periods:
            raise DslEvalError(
                f"CHANGE requires at least {periods + 1} elements in series; "
                f"got {len(series)}."
            )
        base = series[-periods - 1]
        if base == 0.0:
            raise DslEvalError(
                "CHANGE: base value (series[-periods]) is zero; cannot compute "
                "relative change."
            )
        return (series[-1] - base) / base

    @staticmethod
    def cagr(series: list[float], years: float) -> float:
        """Return the Compound Annual Growth Rate over *years* years.

        Formula: ``(series[-1] / series[0]) ^ (1 / years) - 1``

        Parameters
        ----------
        series:
            Time-ordered value series with at least 2 elements.
        years:
            Number of years for the CAGR calculation (must be > 0).

        Raises
        ------
        DslEvalError
            When series has fewer than 2 elements, start value is zero, or
            years is zero.
        """
        if len(series) < 2:
            raise DslEvalError(
                f"CAGR requires at least 2 elements in series; got {len(series)}."
            )
        if years == 0.0:
            raise DslEvalError("CAGR: years must be non-zero.")
        start = series[0]
        if start == 0.0:
            raise DslEvalError(
                "CAGR: start value (series[0]) is zero; cannot compute growth rate."
            )
        return (series[-1] / start) ** (1.0 / years) - 1.0

    @staticmethod
    def corr(series_a: list[float], series_b: list[float]) -> float:
        """Return the Pearson correlation coefficient between *series_a* and *series_b*.

        Result is in [-1.0, 1.0].

        Parameters
        ----------
        series_a, series_b:
            Two series of equal length with at least 2 elements each.

        Raises
        ------
        DslEvalError
            When series are shorter than 2 elements, lengths differ, or either
            series has zero standard deviation (constant series).
        """
        if len(series_a) < 2 or len(series_b) < 2:
            raise DslEvalError(
                "CORR requires series with at least 2 elements each."
            )
        if len(series_a) != len(series_b):
            raise DslEvalError(
                f"CORR requires series of equal length; got {len(series_a)} "
                f"and {len(series_b)}."
            )
        n = len(series_a)
        mean_a = sum(series_a) / n
        mean_b = sum(series_b) / n

        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(series_a, series_b))
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in series_a))
        std_b = math.sqrt(sum((b - mean_b) ** 2 for b in series_b))

        if std_a == 0.0 or std_b == 0.0:
            raise DslEvalError(
                "CORR: one or both series has zero standard deviation (constant series); "
                "Pearson correlation is undefined."
            )
        result = cov / (std_a * std_b)
        # Clamp to [-1.0, 1.0] to handle floating-point rounding at extremes
        return max(-1.0, min(1.0, result))

    @staticmethod
    def zscore(series: list[float]) -> float:
        """Return the z-score of the last element of *series*.

        Formula: ``(series[-1] - mean(series)) / stdev(series)``

        Uses population standard deviation (divisor N) for consistency with
        the plan specification.

        Parameters
        ----------
        series:
            Time-ordered series with at least 2 elements.

        Raises
        ------
        DslEvalError
            When the series has fewer than 2 elements or has zero standard
            deviation (all elements identical).
        """
        if len(series) < 2:
            raise DslEvalError(
                f"ZSCORE requires at least 2 elements in series; got {len(series)}."
            )
        n = len(series)
        mean = sum(series) / n
        variance = sum((x - mean) ** 2 for x in series) / n  # population variance
        std = math.sqrt(variance)

        if std == 0.0:
            raise DslEvalError(
                "ZSCORE: series has zero standard deviation (all elements are identical); "
                "z-score is undefined."
            )
        return (series[-1] - mean) / std
