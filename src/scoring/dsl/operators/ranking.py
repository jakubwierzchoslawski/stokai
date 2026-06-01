"""Ranking operator implementations for the scoring DSL (PLAN-F-003 TASK-006).

Provides RankingOps — pure static methods for RANK_SECTOR and PERCENTILE.

All methods are pure functions: no I/O, no DB, no mutable state.
Empty peer lists raise ``DslEvalError``.
"""
from __future__ import annotations

from src.scoring.exceptions import DslEvalError


class RankingOps:
    """Pure static ranking operator registry."""

    @staticmethod
    def rank_sector(value: float, peer_values: list[float]) -> float:
        """Return the 1-based ascending rank of *value* among *peer_values*.

        The rank is computed as the number of peer values that are strictly
        less than *value*, plus 1.  Ties receive the same rank (dense ranking
        not implemented — standard competition ranking).

        Parameters
        ----------
        value:
            The scalar to rank.
        peer_values:
            The full set of peers (must be non-empty).

        Returns
        -------
        float
            Rank ∈ [1.0, len(peer_values)].

        Raises
        ------
        DslEvalError
            When *peer_values* is empty.
        """
        if not peer_values:
            raise DslEvalError(
                "RANK_SECTOR requires a non-empty peer_values list."
            )
        rank = sum(1.0 for p in peer_values if p < value) + 1.0
        return rank

    @staticmethod
    def percentile(value: float, peer_values: list[float]) -> float:
        """Return the percentile rank of *value* in the *peer_values* distribution.

        Uses the formula: percentile = (count of peers < value) / (n - 1) * 100
        when n > 1, otherwise 0.0 for a single-element peer list.

        Result is always in [0.0, 100.0].

        Parameters
        ----------
        value:
            The scalar to rank.
        peer_values:
            The full set of peers (must be non-empty).

        Raises
        ------
        DslEvalError
            When *peer_values* is empty.
        """
        if not peer_values:
            raise DslEvalError(
                "PERCENTILE requires a non-empty peer_values list."
            )
        n = len(peer_values)
        if n == 1:
            return 0.0
        count_below = sum(1.0 for p in peer_values if p < value)
        return (count_below / (n - 1)) * 100.0
