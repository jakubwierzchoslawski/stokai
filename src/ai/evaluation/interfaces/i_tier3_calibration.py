"""
ITier3Calibration — abstract interface for Tier-3 calibration runs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.ai.evaluation.schemas.calibration_schemas import CalibrationPassResult


class ITier3Calibration(ABC):
    """Runs daily calibration checks comparing confidence to actual outcomes."""

    @abstractmethod
    async def run_calibration(self, reference_date: date) -> CalibrationPassResult:
        """
        Run calibration for the given reference_date.

        Steps:
        1. Load recommendation_outcome rows where generated_at::date = reference_date
           and filled_at IS NOT NULL.
        2. Compute per-signal metrics: direction_correct_pct, mean_confidence,
           mean_actual_t1d, corr_confidence_actual (stats.correlation, or None if
           < 2 samples or zero variance).
        3. Skip signal groups with < 5 rows (debug log).
        4. Upsert calibration_result per signal.
        5. Compute rolling correlation over last 30 days.
        6. below_threshold = rolling_corr < 0.3 when total >= 30, else None.
        """
        ...
