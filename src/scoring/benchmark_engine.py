"""Benchmark engine: retrieves peer scores and computes statistics for normalization."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class InsufficientPeerDataError(Exception):
    """Raised when there are not enough peers to compute meaningful statistics."""


# ---------------------------------------------------------------------------
# Statistics dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkStats:
    mean: float
    std: float
    min: float
    max: float
    p25: float
    p50: float
    p75: float
    p90: float
    p99: float


# ---------------------------------------------------------------------------
# Repository protocols (subset needed by benchmark engine)
# ---------------------------------------------------------------------------

@runtime_checkable
class ICompanyScoreRepositoryForBenchmark(Protocol):
    async def get_peer_scores(
        self, indicator_id: UUID, peer_group: str, tenant_id: UUID
    ) -> list[float]: ...


@runtime_checkable
class IIndicatorRepositoryForBenchmark(Protocol):
    async def get_by_id(self, indicator_id: UUID, tenant_id: UUID) -> object | None: ...


# ---------------------------------------------------------------------------
# Benchmark engine
# ---------------------------------------------------------------------------

class BenchmarkEngine:
    """Provides peer value sets and statistical summaries for normalization.

    Accepts ICompanyScoreRepository and IIndicatorRepository via constructor
    injection — no direct DB access.
    """

    _MIN_PEERS = 2

    def __init__(
        self,
        score_repository: ICompanyScoreRepositoryForBenchmark,
        indicator_repository: IIndicatorRepositoryForBenchmark,
    ) -> None:
        self._score_repo = score_repository
        self._indicator_repo = indicator_repository

    async def get_peer_values(
        self,
        indicator_id: UUID,
        peer_group: str,
        tenant_id: UUID,
    ) -> list[float]:
        """Fetch raw score values for all companies in *peer_group* for this indicator.

        Returns:
            List of float score values.

        Raises:
            InsufficientPeerDataError: if fewer than 2 peer values are available.
        """
        values = await self._score_repo.get_peer_scores(indicator_id, peer_group, tenant_id)
        if len(values) < self._MIN_PEERS:
            raise InsufficientPeerDataError(
                f"Need at least {self._MIN_PEERS} peer values for indicator "
                f"{indicator_id}; got {len(values)}."
            )
        return values

    def compute_benchmark_stats(self, peer_values: list[float]) -> BenchmarkStats:
        """Compute summary statistics over *peer_values*.

        Args:
            peer_values: list of raw score floats.

        Returns:
            BenchmarkStats with mean, std, min, max, p25, p50, p75, p90, p99.

        Raises:
            InsufficientPeerDataError: if fewer than 2 values provided.
        """
        if len(peer_values) < self._MIN_PEERS:
            raise InsufficientPeerDataError(
                f"Need at least {self._MIN_PEERS} peer values; got {len(peer_values)}."
            )

        sorted_vals = sorted(peer_values)
        n = len(sorted_vals)

        mean = sum(sorted_vals) / n
        variance = sum((x - mean) ** 2 for x in sorted_vals) / n
        std = math.sqrt(variance)

        def percentile(p: float) -> float:
            idx = (p / 100.0) * (n - 1)
            lo = int(idx)
            hi = min(lo + 1, n - 1)
            frac = idx - lo
            return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])

        return BenchmarkStats(
            mean=mean,
            std=std,
            min=sorted_vals[0],
            max=sorted_vals[-1],
            p25=percentile(25),
            p50=percentile(50),
            p75=percentile(75),
            p90=percentile(90),
            p99=percentile(99),
        )
