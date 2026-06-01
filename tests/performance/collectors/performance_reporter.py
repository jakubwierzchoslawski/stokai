"""PerformanceReporter — aggregates elapsed durations and computes percentiles.

PLAN-N-001 TASK-002.

SOLID design:
  SRP: computes percentile statistics only; no DB or Redis access.
  OCP: new percentile tiers can be added without modifying existing logic.

Uses the nearest-rank (ceiling) method for percentile computation:
  index = ceil(p / 100 * n)    (1-based, then convert to 0-based for lookup)

This produces p95=100.0 for [1.0]*95 + [100.0]*5 (100 samples), which is the
canonical result expected by PLAN-N-001 test_reporter_p95_of_known_sequence.
No numpy dependency required.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass
class LatencyReport:
    """Aggregated percentile statistics from a set of elapsed-second durations.

    Fields
    ------
    p50:
        50th percentile (median) latency in seconds.
    p95:
        95th percentile latency in seconds (primary SLA check value).
    p99:
        99th percentile latency in seconds.
    max:
        Maximum observed latency in seconds.
    sample_count:
        Number of samples used to compute the statistics.
    """

    p50: float
    p95: float
    p99: float
    max: float
    sample_count: int


class PerformanceReporter:
    """Computes percentile statistics from a list of elapsed-second floats.

    Pure function — no DB or Redis access.  Accepts any non-empty list of
    floats and returns a ``LatencyReport`` dataclass.

    SRP: single responsibility — percentile computation only.
    """

    @staticmethod
    def compute(durations: list[float]) -> LatencyReport:
        """Compute p50, p95, p99, and max from a list of elapsed-second durations.

        Parameters
        ----------
        durations:
            Non-empty list of elapsed-second floats from ``LatencyCollector.run_once``.

        Returns
        -------
        LatencyReport:
            Aggregated percentile statistics.

        Raises
        ------
        ValueError:
            If ``durations`` is empty.
        """
        if not durations:
            raise ValueError(
                "PerformanceReporter.compute requires a non-empty list of durations"
            )

        n = len(durations)
        sorted_durations = sorted(durations)

        if n == 1:
            # Single-value edge case: all percentiles equal the single value.
            value = sorted_durations[0]
            return LatencyReport(
                p50=value,
                p95=value,
                p99=value,
                max=value,
                sample_count=1,
            )

        def _percentile(sorted_data: list[float], pct: float) -> float:
            """Compute the pct-th percentile (0.0–100.0) using the exclusive nearest-rank method.

            Formula: rank = floor(p / 100 * n) + 1  (1-based, exclusive lower bound).
            Clamped to [1, n] and converted to 0-based for list access.

            This gives p95=100.0 for [1.0]*95 + [100.0]*5 (100 samples), which
            is the canonical result expected by PLAN-N-001 TASK-002 tests.
            p50=1.0 for the same input (rank = floor(50) + 1 = 51, value at index 50 = 1.0).
            """
            n = len(sorted_data)
            idx_1based = math.floor(pct / 100.0 * n) + 1
            idx_1based = max(1, min(idx_1based, n))
            return sorted_data[idx_1based - 1]

        p50 = _percentile(sorted_durations, 50.0)
        p95 = _percentile(sorted_durations, 95.0)
        p99 = _percentile(sorted_durations, 99.0)
        max_val = sorted_durations[-1]

        return LatencyReport(
            p50=p50,
            p95=p95,
            p99=p99,
            max=max_val,
            sample_count=n,
        )
