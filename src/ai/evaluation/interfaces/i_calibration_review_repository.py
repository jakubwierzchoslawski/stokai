"""
ICalibrationReviewRepository — abstract interface for calibration_review persistence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.ai.evaluation.schemas.calibration_review_schemas import (
    CalibrationReview,
    CalibrationReviewCreate,
)


class ICalibrationReviewRepository(ABC):
    """Abstract repository for calibration review records."""

    @abstractmethod
    async def insert_review(self, review: CalibrationReviewCreate) -> CalibrationReview:
        """Insert a new calibration review row and return it with generated fields."""
        ...

    @abstractmethod
    async def list_recent(self, limit: int = 10) -> list[CalibrationReview]:
        """Return the most recent calibration reviews, ordered by reviewed_at DESC."""
        ...

    @abstractmethod
    async def get_last_review(self) -> CalibrationReview | None:
        """Return the most recent review, or None if no reviews exist."""
        ...
