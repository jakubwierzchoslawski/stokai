"""
Unit tests for BriefService and BriefFeedbackService (PLAN-F-026 TASK-002).

TDD — all tests written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.briefs.schemas.brief_schemas import (
    BriefFeedbackCreate,
    BriefListResult,
    BriefProjection,
    BriefType,
)
from src.briefs.services.brief_feedback_service import (
    BriefFeedbackService,
    BriefFeedbackValidationError,
)
from src.briefs.services.brief_service import BriefNotFoundError, BriefService


# ── Helpers ───────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
BRIEF_ID = uuid.uuid4()
FEEDBACK_ID = uuid.uuid4()


def _make_projection(
    brief_id: uuid.UUID = None,
    confidence: float = 0.85,
    low_sample: bool = False,
) -> BriefProjection:
    return BriefProjection(
        brief_id=brief_id or uuid.uuid4(),
        type=BriefType.morning_brief,
        headline="Test Headline",
        content_html="<p>Content</p>",
        confidence=confidence,
        sample_size=10 if not low_sample else 3,
        low_sample=low_sample,
        delivery_status="COMPLETED",
        sent_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_feedback_service(
    feedback_repo: AsyncMock = None,
    golden_repo: AsyncMock = None,
) -> BriefFeedbackService:
    from src.ai.memory.schemas.feedback_schemas import UserFeedback

    if feedback_repo is None:
        feedback_repo = AsyncMock()
        feedback = UserFeedback(
            feedback_id=FEEDBACK_ID,
            tenant_id=TENANT_ID,
            feedback_type="thumbs_down",
            source="in_app",
            submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        feedback_repo.append_feedback = AsyncMock(return_value=feedback)

    if golden_repo is None:
        golden_repo = AsyncMock()
        golden_candidate = MagicMock()
        golden_repo.create_candidate = AsyncMock(return_value=golden_candidate)

    return BriefFeedbackService(
        feedback_repository=feedback_repo,
        golden_dataset_repository=golden_repo,
    )


# ── BriefService Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_briefs_returns_mapped_result_with_cursor():
    """Service maps all projections and cursor from repository."""
    projections = [_make_projection() for _ in range(5)]
    mock_cursor = "cursor_abc"

    mock_repo = AsyncMock()
    mock_repo.list_briefs = AsyncMock(return_value=(projections, mock_cursor))

    service = BriefService(brief_repository=mock_repo)
    result = await service.list_briefs(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        brief_type=None,
        cursor=None,
        limit=10,
    )

    assert isinstance(result, BriefListResult)
    assert len(result.items) == 5
    assert result.next_cursor == mock_cursor
    # All fields preserved
    for item in result.items:
        assert item.confidence == 0.85
        assert item.low_sample is False


@pytest.mark.asyncio
async def test_get_brief_detail_raises_not_found_when_repo_returns_none():
    """Service raises BriefNotFoundError when repository returns None."""
    mock_repo = AsyncMock()
    mock_repo.get_brief = AsyncMock(return_value=None)

    service = BriefService(brief_repository=mock_repo)

    with pytest.raises(BriefNotFoundError):
        await service.get_brief_detail(
            brief_id=BRIEF_ID,
            user_id=USER_ID,
            tenant_id=TENANT_ID,
        )


@pytest.mark.asyncio
async def test_get_brief_detail_returns_projection_when_found():
    """Service returns projection from repository."""
    projection = _make_projection(brief_id=BRIEF_ID, confidence=0.92)
    mock_repo = AsyncMock()
    mock_repo.get_brief = AsyncMock(return_value=projection)

    service = BriefService(brief_repository=mock_repo)
    result = await service.get_brief_detail(
        brief_id=BRIEF_ID,
        user_id=USER_ID,
        tenant_id=TENANT_ID,
    )

    assert result.brief_id == BRIEF_ID
    assert result.confidence == 0.92


# ── BriefFeedbackService Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_thumbs_down_calls_feedback_repository():
    """thumbs_down feedback calls append_feedback with correct args; no golden write."""
    from src.ai.memory.schemas.feedback_schemas import UserFeedback

    feedback_repo = AsyncMock()
    feedback = UserFeedback(
        feedback_id=FEEDBACK_ID,
        tenant_id=TENANT_ID,
        feedback_type="thumbs_down",
        source="in_app",
        submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    feedback_repo.append_feedback = AsyncMock(return_value=feedback)

    golden_repo = AsyncMock()
    golden_repo.create_candidate = AsyncMock()

    service = BriefFeedbackService(
        feedback_repository=feedback_repo,
        golden_dataset_repository=golden_repo,
    )

    payload = BriefFeedbackCreate(feedback_type="thumbs_down")
    await service.submit_feedback(
        brief_id=BRIEF_ID,
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        payload=payload,
    )

    feedback_repo.append_feedback.assert_called_once()
    call_args = feedback_repo.append_feedback.call_args[0][0]
    assert str(call_args.report_id) == str(BRIEF_ID)
    assert call_args.feedback_type.value == "thumbs_down"

    # golden repo must NOT be called for non-edit feedback
    golden_repo.create_candidate.assert_not_called()


@pytest.mark.asyncio
async def test_submit_edit_calls_both_repositories():
    """Edit feedback calls both append_feedback and create_candidate."""
    from src.ai.memory.schemas.feedback_schemas import UserFeedback

    feedback_repo = AsyncMock()
    feedback = UserFeedback(
        feedback_id=FEEDBACK_ID,
        tenant_id=TENANT_ID,
        feedback_type="edit",
        source="in_app",
        submitted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    feedback_repo.append_feedback = AsyncMock(return_value=feedback)

    golden_repo = AsyncMock()
    golden_candidate = MagicMock()
    golden_repo.create_candidate = AsyncMock(return_value=golden_candidate)

    service = BriefFeedbackService(
        feedback_repository=feedback_repo,
        golden_dataset_repository=golden_repo,
    )

    correction_text = "The correct analysis should be..."
    payload = BriefFeedbackCreate(feedback_type="edit", correction=correction_text)
    await service.submit_feedback(
        brief_id=BRIEF_ID,
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        payload=payload,
        original_content="<p>Original</p>",
    )

    feedback_repo.append_feedback.assert_called_once()
    golden_repo.create_candidate.assert_called_once()

    candidate_arg = golden_repo.create_candidate.call_args[0][0]
    assert str(candidate_arg.brief_id) == str(BRIEF_ID)
    assert candidate_arg.correction == correction_text


@pytest.mark.asyncio
async def test_submit_edit_without_correction_raises_validation_error():
    """Edit feedback without correction raises BriefFeedbackValidationError."""
    service = _make_feedback_service()

    payload = BriefFeedbackCreate(feedback_type="edit", correction=None)
    with pytest.raises(BriefFeedbackValidationError):
        await service.submit_feedback(
            brief_id=BRIEF_ID,
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            payload=payload,
        )


@pytest.mark.asyncio
async def test_submit_edit_with_empty_correction_raises_validation_error():
    """Edit feedback with empty string correction raises BriefFeedbackValidationError."""
    service = _make_feedback_service()

    payload = BriefFeedbackCreate(feedback_type="edit", correction="")
    with pytest.raises(BriefFeedbackValidationError):
        await service.submit_feedback(
            brief_id=BRIEF_ID,
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            payload=payload,
        )
