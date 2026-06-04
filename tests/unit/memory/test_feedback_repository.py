"""
Unit tests for FeedbackRepository using mocked async sessions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.memory.repositories.feedback_repository import FeedbackRepository
from src.ai.memory.schemas.feedback_schemas import (
    FeedbackSource,
    FeedbackType,
    UserFeedbackCreate,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


def _make_feedback_orm(feedback_type: str = "thumbs_down", source: str = "in_app"):
    from src.ai.memory.models.feedback_models import UserFeedback as Orm
    orm = MagicMock(spec=Orm)
    orm.feedback_id = uuid.uuid4()
    orm.tenant_id = uuid.uuid4()
    orm.report_id = uuid.uuid4()
    orm.recommendation_id = None
    orm.feedback_type = feedback_type
    orm.feedback_text = "Not relevant"
    orm.user_edit = None
    orm.reviewer_id = None
    orm.source = source
    orm.submitted_at = datetime.now(tz=timezone.utc)
    return orm


# ── append_feedback ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_feedback_thumbs_down_in_app_inserts_correctly():
    session = _make_session()
    fb_orm = _make_feedback_orm()

    async def fake_refresh(obj):
        obj.feedback_id = fb_orm.feedback_id
        obj.tenant_id = fb_orm.tenant_id
        obj.report_id = fb_orm.report_id
        obj.recommendation_id = None
        obj.feedback_type = "thumbs_down"
        obj.feedback_text = "Not relevant"
        obj.user_edit = None
        obj.reviewer_id = None
        obj.source = "in_app"
        obj.submitted_at = fb_orm.submitted_at

    session.refresh.side_effect = fake_refresh

    repo = FeedbackRepository(session)
    fb_create = UserFeedbackCreate(
        tenant_id=uuid.uuid4(),
        report_id=uuid.uuid4(),
        feedback_type=FeedbackType.THUMBS_DOWN,
        feedback_text="Not relevant",
        source=FeedbackSource.IN_APP,
    )

    result = await repo.append_feedback(fb_create)

    session.add.assert_called_once()
    session.flush.assert_called()
    assert result.feedback_type == "thumbs_down"
    assert result.source == "in_app"


# ── list_since ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_since_returns_only_feedback_after_threshold():
    session = _make_session()
    fb_orm = _make_feedback_orm()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fb_orm]
    session.execute.return_value = mock_result

    repo = FeedbackRepository(session)
    since = datetime.now(tz=timezone.utc) - timedelta(days=7)
    results = await repo.list_since(since=since)

    assert len(results) == 1
    session.execute.assert_called_once()


# ── get_feedback_for_report ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_feedback_for_report_returns_all_feedback_for_report_id():
    session = _make_session()
    report_id = uuid.uuid4()
    fb_orm_1 = _make_feedback_orm()
    fb_orm_1.report_id = report_id
    fb_orm_2 = _make_feedback_orm(feedback_type="thumbs_up")
    fb_orm_2.report_id = report_id

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fb_orm_1, fb_orm_2]
    session.execute.return_value = mock_result

    repo = FeedbackRepository(session)
    results = await repo.get_feedback_for_report(report_id=report_id)

    assert len(results) == 2
