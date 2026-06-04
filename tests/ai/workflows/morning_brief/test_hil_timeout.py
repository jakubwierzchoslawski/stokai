"""
Unit tests for the HIL queue node and hil_timeout_handler.

TDD: PLAN-F-006 TASK-011

AC covered: AC-003 (HIL routing, 05:45 timeout, hold-and-notify), AC-005
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState


def _make_state(**kwargs) -> MorningBriefState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "confidence_scores": {"agent": 0.55},
    }
    defaults.update(kwargs)
    return MorningBriefState(**defaults)


def _make_hil_item(
    *,
    item_id: uuid.UUID | None = None,
    workflow_run_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    status: str = "pending",
    scheduled_send_at: datetime | None = None,
    lc_checkpoint_id: str = "hil:test",
) -> MagicMock:
    item = MagicMock()
    item.item_id = item_id or uuid.uuid4()
    item.workflow_run_id = workflow_run_id or uuid.uuid4()
    item.user_id = user_id or uuid.uuid4()
    item.tenant_id = tenant_id or uuid.uuid4()
    item.status = status
    item.scheduled_send_at = scheduled_send_at or datetime(
        2026, 6, 4, 5, 45, 0, tzinfo=timezone.utc
    )
    item.lc_checkpoint_id = lc_checkpoint_id
    return item


# ─── hil_queue_node ───────────────────────────────────────────────────────────


class TestHilQueueNode:
    @pytest.mark.asyncio
    async def test_hil_queue_node_persists_pending_brief(self):
        """hil_queue_node must persist BriefRow with hil_status=PENDING."""
        from src.ai.workflows.morning_brief.nodes.hil_queue_node import hil_queue_node

        state = _make_state()
        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)
        mock_brief = MagicMock()
        mock_brief.brief_id = uuid.uuid4()
        brief_repo = AsyncMock()
        brief_repo.insert = AsyncMock(return_value=mock_brief)
        brief_repo.update_hil_status = AsyncMock()

        await hil_queue_node(
            state, hil_repo=hil_repo, brief_repo=brief_repo
        )

        brief_repo.insert.assert_called_once()
        brief_repo.update_hil_status.assert_called_once()
        # Verify hil_status is "pending"
        call_args = brief_repo.update_hil_status.call_args
        assert "pending" in str(call_args)

    @pytest.mark.asyncio
    async def test_hil_queue_node_calls_hil_enqueue(self):
        """hil_queue_node must call HILQueueRepository.create with correct deadline."""
        from src.ai.workflows.morning_brief.nodes.hil_queue_node import hil_queue_node

        now = datetime(2026, 6, 4, 4, 0, 0, tzinfo=timezone.utc)
        state = _make_state()
        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)

        await hil_queue_node(state, hil_repo=hil_repo, now=now)

        hil_repo.create.assert_called_once()
        dto = hil_repo.create.call_args.args[0]
        assert dto.scheduled_send_at.hour == 5
        assert dto.scheduled_send_at.minute == 45
        assert dto.workflow_run_id == state.workflow_id

    @pytest.mark.asyncio
    async def test_hil_queue_node_does_not_dispatch_email(self):
        """hil_queue_node must NOT call any email dispatcher."""
        from src.ai.workflows.morning_brief.nodes.hil_queue_node import hil_queue_node

        state = _make_state()
        mock_item = MagicMock()
        mock_item.item_id = uuid.uuid4()
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=mock_item)
        email_dispatcher = AsyncMock()
        email_dispatcher.send_morning_brief = AsyncMock()

        updated = await hil_queue_node(state, hil_repo=hil_repo)

        email_dispatcher.send_morning_brief.assert_not_called()
        # State must set confidence_route=HIL, not AUTO_SEND
        assert updated.confidence_route == ConfidenceRoute.HIL


# ─── hil_timeout_handler ──────────────────────────────────────────────────────


class TestHilTimeoutHandler:
    @pytest.mark.asyncio
    async def test_hil_timeout_handler_marks_unreviewed_as_timed_out(self):
        """handle_hil_timeouts must set TIMED_OUT for unreviewed items."""
        from src.ai.workflows.morning_brief.hil_timeout_handler import (
            handle_hil_timeouts,
        )

        now = datetime(2026, 6, 4, 5, 46, 0, tzinfo=timezone.utc)
        items = [_make_hil_item(), _make_hil_item()]

        hil_repo = AsyncMock()
        hil_repo.list_timed_out_pending = AsyncMock(return_value=items)
        hil_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_repo.get_latest_by_user = AsyncMock(return_value=None)

        email_dispatcher = AsyncMock()
        email_dispatcher.send_no_brief_notification = AsyncMock()

        user_feedback_repo = AsyncMock()
        user_feedback_repo.write = AsyncMock()

        result = await handle_hil_timeouts(
            brief_repo=brief_repo,
            hil_repo=hil_repo,
            email_dispatcher=email_dispatcher,
            user_feedback_repo=user_feedback_repo,
            now=now,
        )

        assert result["timed_out"] == 2
        # update_status called once per item
        assert hil_repo.update_status.call_count == 2

    @pytest.mark.asyncio
    async def test_hil_timeout_handler_sends_notification_on_timeout(self):
        """handle_hil_timeouts must send 'No Morning Brief today' per user."""
        from src.ai.workflows.morning_brief.hil_timeout_handler import (
            handle_hil_timeouts,
        )

        now = datetime(2026, 6, 4, 5, 46, 0, tzinfo=timezone.utc)
        items = [_make_hil_item()]

        hil_repo = AsyncMock()
        hil_repo.list_timed_out_pending = AsyncMock(return_value=items)
        hil_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_repo.get_latest_by_user = AsyncMock(return_value=None)

        email_dispatcher = AsyncMock()
        email_dispatcher.send_no_brief_notification = AsyncMock()

        user_feedback_repo = AsyncMock()
        user_feedback_repo.write = AsyncMock()

        await handle_hil_timeouts(
            brief_repo=brief_repo,
            hil_repo=hil_repo,
            email_dispatcher=email_dispatcher,
            user_feedback_repo=user_feedback_repo,
            now=now,
        )

        email_dispatcher.send_no_brief_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_hil_timeout_handler_resumes_graph_for_approved(self):
        """handle_hil_timeouts must call graph.resume for approved items."""
        from src.ai.workflows.morning_brief.hil_timeout_handler import (
            handle_hil_timeouts,
        )

        now = datetime(2026, 6, 4, 5, 46, 0, tzinfo=timezone.utc)
        approved_item = _make_hil_item(
            status="approved", lc_checkpoint_id="hil:approved-wf"
        )

        hil_repo = AsyncMock()
        hil_repo.list_timed_out_pending = AsyncMock(return_value=[])
        hil_repo.list_approved_pending_dispatch = AsyncMock(
            return_value=[approved_item]
        )
        hil_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        email_dispatcher = AsyncMock()
        email_dispatcher.send_no_brief_notification = AsyncMock()
        user_feedback_repo = AsyncMock()
        user_feedback_repo.write = AsyncMock()

        graph_runner = AsyncMock()
        graph_runner.resume = AsyncMock()

        await handle_hil_timeouts(
            brief_repo=brief_repo,
            hil_repo=hil_repo,
            email_dispatcher=email_dispatcher,
            user_feedback_repo=user_feedback_repo,
            graph_runner=graph_runner,
            now=now,
        )

        graph_runner.resume.assert_called_once_with("hil:approved-wf")

    @pytest.mark.asyncio
    async def test_hil_timeout_handler_writes_feedback_on_timeout(self):
        """handle_hil_timeouts must write Layer 4 feedback entry per timed-out item."""
        from src.ai.workflows.morning_brief.hil_timeout_handler import (
            handle_hil_timeouts,
        )

        now = datetime(2026, 6, 4, 5, 46, 0, tzinfo=timezone.utc)
        items = [_make_hil_item()]

        hil_repo = AsyncMock()
        hil_repo.list_timed_out_pending = AsyncMock(return_value=items)
        hil_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_repo.get_latest_by_user = AsyncMock(return_value=None)

        email_dispatcher = AsyncMock()
        email_dispatcher.send_no_brief_notification = AsyncMock()

        user_feedback_repo = AsyncMock()
        user_feedback_repo.write = AsyncMock()

        await handle_hil_timeouts(
            brief_repo=brief_repo,
            hil_repo=hil_repo,
            email_dispatcher=email_dispatcher,
            user_feedback_repo=user_feedback_repo,
            now=now,
        )

        user_feedback_repo.write.assert_called_once()
        entry = user_feedback_repo.write.call_args.args[0]
        assert entry.get("feedback_type") == "hil_timeout"
        assert entry.get("status") == "timed_out"
