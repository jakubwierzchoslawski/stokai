"""
Unit tests for Morning Brief routing/terminal nodes.

TDD: written before implementation — PLAN-F-006 TASK-005.

Tests:
  - hil_queue: enqueues in HIL with correct deadline (05:45 UTC), sets requires_hil
  - block_and_log: logs WARNING, sets BLOCK route, does not dispatch email
  - dispatch_brief: inserts Brief row, sends email, sets brief_id and AUTO_SEND route
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState
from src.ai.workflows.morning_brief_nodes import (
    block_and_log,
    dispatch_brief,
    hil_queue,
    _compute_hil_deadline,
)


def _make_state(**kwargs) -> MorningBriefState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "confidence_scores": {"analyst": 0.55},
    }
    defaults.update(kwargs)
    return MorningBriefState(**defaults)


class TestHilQueue:
    @pytest.mark.asyncio
    async def test_hil_queue_enqueues_with_correct_deadline(self):
        """hil_queue must enqueue with deadline at next 05:45 UTC."""
        state = _make_state()
        now = datetime(2026, 6, 4, 4, 0, 0, tzinfo=timezone.utc)  # before 05:45

        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)

        updated = await hil_queue(state, hil_repo=hil_repo, now=now)

        # Check item was created
        hil_repo.create.assert_called_once()
        call_dto = hil_repo.create.call_args.args[0]

        # Deadline must be 05:45 same day since we're at 04:00
        assert call_dto.scheduled_send_at.hour == 5
        assert call_dto.scheduled_send_at.minute == 45

    @pytest.mark.asyncio
    async def test_hil_queue_advances_to_next_day_when_past_deadline(self):
        """hil_queue must use next-day 05:45 UTC if today's has passed."""
        state = _make_state()
        now = datetime(2026, 6, 4, 6, 0, 0, tzinfo=timezone.utc)  # after 05:45

        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)

        await hil_queue(state, hil_repo=hil_repo, now=now)

        call_dto = hil_repo.create.call_args.args[0]
        # Must be the NEXT day at 05:45
        assert call_dto.scheduled_send_at.day == 5  # June 5

    @pytest.mark.asyncio
    async def test_hil_queue_sets_requires_hil_true(self):
        """hil_queue must set requires_hil=True on the returned state."""
        state = _make_state()
        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)

        updated = await hil_queue(state, hil_repo=hil_repo)

        assert updated.requires_hil is True

    @pytest.mark.asyncio
    async def test_hil_queue_sets_confidence_route_hil(self):
        """hil_queue must set confidence_route=HIL on the returned state."""
        state = _make_state()
        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)

        updated = await hil_queue(state, hil_repo=hil_repo)

        assert updated.confidence_route == ConfidenceRoute.HIL

    @pytest.mark.asyncio
    async def test_hil_queue_enqueues_with_workflow_run_id(self):
        """hil_queue must set workflow_run_id on the HIL queue item."""
        state = _make_state()
        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)

        await hil_queue(state, hil_repo=hil_repo)

        call_dto = hil_repo.create.call_args.args[0]
        assert call_dto.workflow_run_id == state.workflow_id
        assert call_dto.workflow_type == "morning_brief"


class TestBlockAndLog:
    @pytest.mark.asyncio
    async def test_block_and_log_sets_block_route(self):
        """block_and_log must set confidence_route=BLOCK."""
        state = _make_state()
        updated = await block_and_log(state)
        assert updated.confidence_route == ConfidenceRoute.BLOCK

    @pytest.mark.asyncio
    async def test_block_and_log_does_not_dispatch(self):
        """block_and_log must NOT set brief_id (no dispatch)."""
        state = _make_state()
        updated = await block_and_log(state)
        assert updated.brief_id is None

    @pytest.mark.asyncio
    async def test_block_and_log_logs_warning(self, caplog):
        """block_and_log must emit a WARNING log message."""
        import logging
        state = _make_state()

        with caplog.at_level(logging.WARNING, logger="src.ai.workflows.morning_brief_nodes"):
            await block_and_log(state)

        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    @pytest.mark.asyncio
    async def test_block_and_log_does_not_set_requires_hil(self):
        """block_and_log must NOT set requires_hil=True."""
        state = _make_state()
        updated = await block_and_log(state)
        # Should remain False (default)
        assert updated.requires_hil is False


class TestDispatchBrief:
    @pytest.mark.asyncio
    async def test_dispatch_brief_inserts_brief_row(self):
        """dispatch_brief must call brief_repo.insert()."""
        state = _make_state(
            report="<h1>Morning Brief</h1>",
            confidence_scores={"analyst": 0.85},
        )

        mock_brief = MagicMock()
        mock_brief.brief_id = uuid.uuid4()
        brief_repo = AsyncMock()
        brief_repo.insert = AsyncMock(return_value=mock_brief)
        brief_repo.update_sent_at = AsyncMock()

        email_dispatcher = AsyncMock()
        email_dispatcher.send_morning_brief = AsyncMock(return_value=True)

        updated = await dispatch_brief(
            state,
            brief_repo=brief_repo,
            email_dispatcher=email_dispatcher,
            user_email="user@example.com",
        )

        brief_repo.insert.assert_called_once()
        assert updated.brief_id == mock_brief.brief_id

    @pytest.mark.asyncio
    async def test_dispatch_brief_sends_email(self):
        """dispatch_brief must call email_dispatcher.send_morning_brief()."""
        state = _make_state(
            report="<p>Brief</p>",
            confidence_scores={"analyst": 0.90},
        )

        mock_brief = MagicMock()
        mock_brief.brief_id = uuid.uuid4()
        brief_repo = AsyncMock()
        brief_repo.insert = AsyncMock(return_value=mock_brief)
        brief_repo.update_sent_at = AsyncMock()

        email_dispatcher = AsyncMock()
        email_dispatcher.send_morning_brief = AsyncMock(return_value=True)

        await dispatch_brief(
            state,
            brief_repo=brief_repo,
            email_dispatcher=email_dispatcher,
            user_email="trader@example.com",
        )

        email_dispatcher.send_morning_brief.assert_called_once()
        call_kwargs = email_dispatcher.send_morning_brief.call_args.kwargs
        assert call_kwargs["to"] == "trader@example.com"

    @pytest.mark.asyncio
    async def test_dispatch_brief_sets_auto_send_route(self):
        """dispatch_brief must set confidence_route=AUTO_SEND."""
        state = _make_state(report="<p>Brief</p>")

        mock_brief = MagicMock()
        mock_brief.brief_id = uuid.uuid4()
        brief_repo = AsyncMock()
        brief_repo.insert = AsyncMock(return_value=mock_brief)
        brief_repo.update_sent_at = AsyncMock()

        email_dispatcher = AsyncMock()
        email_dispatcher.send_morning_brief = AsyncMock(return_value=True)

        updated = await dispatch_brief(
            state,
            brief_repo=brief_repo,
            email_dispatcher=email_dispatcher,
            user_email="user@example.com",
        )

        assert updated.confidence_route == ConfidenceRoute.AUTO_SEND

    @pytest.mark.asyncio
    async def test_dispatch_brief_updates_sent_at_on_success(self):
        """dispatch_brief must update sent_at on the Brief row when email succeeds."""
        state = _make_state(report="<p>Brief</p>")

        mock_brief = MagicMock()
        mock_brief.brief_id = uuid.uuid4()
        brief_repo = AsyncMock()
        brief_repo.insert = AsyncMock(return_value=mock_brief)
        brief_repo.update_sent_at = AsyncMock()

        email_dispatcher = AsyncMock()
        email_dispatcher.send_morning_brief = AsyncMock(return_value=True)

        await dispatch_brief(
            state,
            brief_repo=brief_repo,
            email_dispatcher=email_dispatcher,
            user_email="user@example.com",
        )

        brief_repo.update_sent_at.assert_called_once()


class TestComputeHilDeadline:
    def test_returns_today_when_before_0545(self):
        """_compute_hil_deadline returns today 05:45 when current time is before it."""
        now = datetime(2026, 6, 4, 4, 30, 0, tzinfo=timezone.utc)
        deadline = _compute_hil_deadline(now)

        assert deadline.hour == 5
        assert deadline.minute == 45
        assert deadline.day == 4

    def test_returns_tomorrow_when_after_0545(self):
        """_compute_hil_deadline returns tomorrow 05:45 when current time is after it."""
        now = datetime(2026, 6, 4, 6, 0, 0, tzinfo=timezone.utc)
        deadline = _compute_hil_deadline(now)

        assert deadline.hour == 5
        assert deadline.minute == 45
        assert deadline.day == 5
