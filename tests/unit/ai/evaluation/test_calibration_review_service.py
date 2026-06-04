"""
Unit tests for TASK-003: CalibrationReviewService.

TDD: tests written before the implementation exists. All external calls are mocked.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.evaluation.schemas.calibration_review_schemas import CalibrationReview


def _make_review(
    review_id: uuid.UUID | None = None,
    reviewed_by: uuid.UUID | None = None,
    action_taken: str = "no_action",
    corr_at_review: float | None = 0.22,
    below_threshold: bool = False,
    notes: str | None = None,
) -> CalibrationReview:
    return CalibrationReview(
        review_id=review_id or uuid.uuid4(),
        reviewed_by=reviewed_by or uuid.uuid4(),
        reviewed_at=datetime.now(tz=timezone.utc),
        corr_at_review=corr_at_review,
        below_threshold=below_threshold,
        action_taken=action_taken,
        notes=notes,
    )


# ── record_review ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_review_with_no_action_inserts_and_returns():
    """record_review with 'no_action' must call insert_review and return CalibrationReview."""
    from src.ai.evaluation.services.calibration_review_service import (
        CalibrationReviewService,
    )

    user_id = uuid.uuid4()
    expected_review = _make_review(reviewed_by=user_id, action_taken="no_action")

    mock_review_repo = AsyncMock()
    mock_review_repo.insert_review = AsyncMock(return_value=expected_review)

    mock_cal_repo = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.22)

    service = CalibrationReviewService(
        review_repo=mock_review_repo,
        calibration_repo=mock_cal_repo,
    )

    result = await service.record_review(
        reviewed_by=user_id,
        action_taken="no_action",
    )

    mock_review_repo.insert_review.assert_called_once()
    assert result.reviewed_by == user_id
    assert result.action_taken == "no_action"
    assert isinstance(result, CalibrationReview)


@pytest.mark.asyncio
async def test_record_review_invalid_action_taken_raises_value_error_before_touching_repo():
    """Invalid action_taken must raise ValueError without calling insert_review."""
    from src.ai.evaluation.services.calibration_review_service import (
        CalibrationReviewService,
    )

    mock_review_repo = AsyncMock()
    mock_review_repo.insert_review = AsyncMock()

    mock_cal_repo = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.22)

    service = CalibrationReviewService(
        review_repo=mock_review_repo,
        calibration_repo=mock_cal_repo,
    )

    with pytest.raises(ValueError, match="action_taken must be one of"):
        await service.record_review(
            reviewed_by=uuid.uuid4(),
            action_taken="INVALID_ACTION",
        )

    mock_review_repo.insert_review.assert_not_called()


@pytest.mark.asyncio
async def test_record_review_logs_structured_info_entry(caplog):
    """record_review must emit a structured INFO log with event='calibration_review_recorded'."""
    from src.ai.evaluation.services.calibration_review_service import (
        CalibrationReviewService,
    )

    user_id = uuid.uuid4()
    expected_review = _make_review(reviewed_by=user_id, action_taken="model_flag")

    mock_review_repo = AsyncMock()
    mock_review_repo.insert_review = AsyncMock(return_value=expected_review)

    mock_cal_repo = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=0.22)

    service = CalibrationReviewService(
        review_repo=mock_review_repo,
        calibration_repo=mock_cal_repo,
    )

    with caplog.at_level(logging.INFO, logger="src.ai.evaluation.services.calibration_review_service"):
        await service.record_review(
            reviewed_by=user_id,
            action_taken="model_flag",
        )

    # At least one INFO record should mention the structured event
    assert any(
        "calibration_review_recorded" in r.getMessage()
        or getattr(r, "event", None) == "calibration_review_recorded"
        for r in caplog.records
    ), f"Expected log with 'calibration_review_recorded', got: {[r.getMessage() for r in caplog.records]}"


@pytest.mark.asyncio
async def test_record_review_reads_corr_from_calibration_repo():
    """record_review must pass corr_at_review obtained from get_rolling_corr to insert_review."""
    from src.ai.evaluation.services.calibration_review_service import (
        CalibrationReviewService,
    )

    user_id = uuid.uuid4()
    expected_corr = 0.22
    expected_review = _make_review(
        reviewed_by=user_id,
        action_taken="no_action",
        corr_at_review=expected_corr,
    )

    mock_review_repo = AsyncMock()
    mock_review_repo.insert_review = AsyncMock(return_value=expected_review)

    mock_cal_repo = AsyncMock()
    mock_cal_repo.get_rolling_corr = AsyncMock(return_value=expected_corr)

    service = CalibrationReviewService(
        review_repo=mock_review_repo,
        calibration_repo=mock_cal_repo,
    )

    await service.record_review(reviewed_by=user_id, action_taken="no_action")

    mock_cal_repo.get_rolling_corr.assert_called_once_with(days=30)
    call_args = mock_review_repo.insert_review.call_args[0][0]
    assert call_args.corr_at_review == expected_corr


# ── list_reviews ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_reviews_delegates_to_repo_list_recent():
    """list_reviews must delegate to repo.list_recent with the given limit."""
    from src.ai.evaluation.services.calibration_review_service import (
        CalibrationReviewService,
    )

    reviews = [_make_review() for _ in range(3)]

    mock_review_repo = AsyncMock()
    mock_review_repo.list_recent = AsyncMock(return_value=reviews)

    mock_cal_repo = AsyncMock()

    service = CalibrationReviewService(
        review_repo=mock_review_repo,
        calibration_repo=mock_cal_repo,
    )

    result = await service.list_reviews(limit=5)

    mock_review_repo.list_recent.assert_called_once_with(limit=5)
    assert result == reviews
