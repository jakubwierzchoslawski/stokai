"""DSL operator registry (PLAN-F-003 TASK-006).

Exports the unified OPERATOR_REGISTRY dict that maps function names to
callables. The evaluator uses this registry exclusively — adding a new
operator requires only a new entry here (OCP).

Binary arithmetic operators (+, -, *, /, ^, comparisons) are dispatched by
the evaluator directly via ArithmeticOps; they do not appear in the function
name registry.

Function name registry (OPERATOR_REGISTRY):
    Logical:    AND, OR, IF
    Ranking:    RANK_SECTOR, PERCENTILE
    Time-series: CHANGE, CAGR, CORR, ZSCORE
"""
from __future__ import annotations

from src.scoring.dsl.operators.logical import LogicalOps
from src.scoring.dsl.operators.ranking import RankingOps
from src.scoring.dsl.operators.timeseries import TimeSeriesOps

# ---------------------------------------------------------------------------
# Unified function-name → callable registry (used by the evaluator)
# Each callable receives *args already evaluated to float or list[float].
# ---------------------------------------------------------------------------

OPERATOR_REGISTRY: dict[str, object] = {
    # Logical
    "AND": LogicalOps.and_op,
    "OR": LogicalOps.or_op,
    "IF": LogicalOps.if_op,
    # Ranking
    "RANK_SECTOR": RankingOps.rank_sector,
    "PERCENTILE": RankingOps.percentile,
    # Time-series
    "CHANGE": TimeSeriesOps.change,
    "CAGR": TimeSeriesOps.cagr,
    "CORR": TimeSeriesOps.corr,
    "ZSCORE": TimeSeriesOps.zscore,
}

__all__ = ["OPERATOR_REGISTRY"]
