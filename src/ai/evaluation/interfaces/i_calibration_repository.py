"""
ICalibrationRepository — abstract interface for calibration_result persistence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.ai.evaluation.schemas.calibration_schemas import (
    CalibrationResult,
    CalibrationResultCreate,
)


class ICalibrationRepository(ABC):
    """Abstract repository for Tier-3 calibration results."""

    @abstractmethod
    async def insert_result(
        self, result: CalibrationResultCreate
    ) -> CalibrationResult:
        """Upsert a calibration result row (ON CONFLICT (date, action_signal) DO UPDATE)."""
        ...

    @abstractmethod
    async def list_last_n_days(
        self, days: int, action_signal: Optional[str] = None
    ) -> list[CalibrationResult]:
        """Return calibration results for the last N days, optionally filtered by signal."""
        ...

    @abstractmethod
    async def get_rolling_corr(self, days: int = 30) -> Optional[float]:
        """Return the rolling average of corr_confidence_actual over the last N days."""
        ...
