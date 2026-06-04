"""
CalibrationReviewService — records and lists admin calibration review decisions.

Weekly review workflow:
  1. Admin calls record_review after inspecting the calibration dashboard.
  2. Service reads current rolling_corr from ICalibrationRepository.
  3. Derives below_threshold from the corr value and settings threshold.
  4. Persists a CalibrationReview row via ICalibrationReviewRepository.
  5. Emits a structured INFO log.
"""
from __future__ import annotations

import logging
from uuid import UUID

from src.ai.evaluation.interfaces.i_calibration_repository import (
    ICalibrationRepository,
)
from src.ai.evaluation.interfaces.i_calibration_review_repository import (
    ICalibrationReviewRepository,
)
from src.ai.evaluation.schemas.calibration_review_schemas import (
    CalibrationReview,
    CalibrationReviewCreate,
    _VALID_ACTIONS,
)
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class CalibrationReviewService:
    """Records and lists weekly admin calibration reviews."""

    def __init__(
        self,
        review_repo: ICalibrationReviewRepository,
        calibration_repo: ICalibrationRepository,
    ) -> None:
        self._review_repo = review_repo
        self._calibration_repo = calibration_repo

    async def record_review(
        self,
        reviewed_by: UUID,
        action_taken: str,
        notes: str | None = None,
    ) -> CalibrationReview:
        """
        Record a weekly calibration review.

        Reads current rolling_corr from the calibration repository, derives
        below_threshold, persists the review row, and emits a structured log.

        Raises ValueError if action_taken is not one of the allowed values.
        """
        if action_taken not in _VALID_ACTIONS:
            raise ValueError(
                f"action_taken must be one of {sorted(_VALID_ACTIONS)}, got {action_taken!r}"
            )

        settings = get_settings()
        _threshold = settings.CALIBRATION_CORR_THRESHOLD

        corr_at_review = await self._calibration_repo.get_rolling_corr(days=30)

        below_threshold = False
        if corr_at_review is not None:
            below_threshold = corr_at_review < _threshold

        create = CalibrationReviewCreate(
            reviewed_by=reviewed_by,
            action_taken=action_taken,
            corr_at_review=corr_at_review,
            below_threshold=below_threshold,
            notes=notes,
        )
        review = await self._review_repo.insert_review(create)

        logger.info(
            "calibration_review_recorded",
            extra={
                "event": "calibration_review_recorded",
                "review_id": str(review.review_id),
                "reviewed_by": str(reviewed_by),
                "action_taken": action_taken,
                "corr_at_review": corr_at_review,
                "below_threshold": below_threshold,
            },
        )

        return review

    async def list_reviews(self, limit: int = 10) -> list[CalibrationReview]:
        """Return the most recent calibration reviews in descending order."""
        return await self._review_repo.list_recent(limit=limit)
