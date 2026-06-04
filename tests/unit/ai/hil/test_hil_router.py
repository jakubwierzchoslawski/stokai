"""
Unit tests for hil_router_edge.

All external dependencies (HILQueueRepository, AsyncPostgresSaver, DB session)
are mocked. No real PostgreSQL or LangGraph runtime required.

TDD tests defined before implementation (PLAN-F-013 TASK-003).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowType
from src.ai.hil.hil_router import hil_router_edge, compute_scheduled_send_at


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_state(
    *,
    requires_hil: bool = False,
    confidence: float = 0.55,
    workflow_type: WorkflowType = WorkflowType.ON_DEMAND,
) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=workflow_type,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=_utcnow(),
        overall_confidence=confidence,
        requires_hil=requires_hil,
        hil_reason="low confidence" if requires_hil else None,
    )


@pytest.mark.asyncio
class TestHilRouterEdge:
    """Tests for hil_router_edge conditional edge function."""

    async def test_routes_to_narrative_writer_when_requires_hil_false(self) -> None:
        state = _make_state(requires_hil=False)

        with (
            patch("src.ai.hil.hil_router.HILQueueRepository") as mock_repo_cls,
            patch("src.ai.hil.hil_router._get_db_session") as mock_session,
        ):
            result = await hil_router_edge(state)

        assert result == "narrative_writer"
        mock_repo_cls.return_value.create.assert_not_called()

    async def test_routes_to_hil_when_requires_hil_true(self) -> None:
        state = _make_state(requires_hil=True)

        mock_repo = AsyncMock()
        created_item = MagicMock()
        created_item.item_id = uuid.uuid4()
        mock_repo.create = AsyncMock(return_value=created_item)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.ai.hil.hil_router.HILQueueRepository", return_value=mock_repo),
            patch("src.ai.hil.hil_router._get_db_session", return_value=mock_session_ctx),
        ):
            result = await hil_router_edge(state)

        assert result == "hil"

    async def test_creates_hil_queue_item_on_hil_route(self) -> None:
        state = _make_state(requires_hil=True, workflow_type=WorkflowType.ON_DEMAND)

        mock_repo = AsyncMock()
        created_item = MagicMock()
        created_item.item_id = uuid.uuid4()
        mock_repo.create = AsyncMock(return_value=created_item)

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.ai.hil.hil_router.HILQueueRepository", return_value=mock_repo),
            patch("src.ai.hil.hil_router._get_db_session", return_value=mock_session_ctx),
        ):
            await hil_router_edge(state)

        mock_repo.create.assert_called_once()
        call_args = mock_repo.create.call_args[0][0]
        assert call_args.tenant_id == state.tenant_id
        assert call_args.workflow_run_id == state.workflow_id
        assert call_args.confidence == state.overall_confidence

    async def test_checkpoint_id_stored_in_queue_item(self) -> None:
        state = _make_state(requires_hil=True)

        mock_repo = AsyncMock()
        created_item = MagicMock()
        created_item.item_id = uuid.uuid4()
        mock_repo.create = AsyncMock(return_value=created_item)

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.ai.hil.hil_router.HILQueueRepository", return_value=mock_repo),
            patch("src.ai.hil.hil_router._get_db_session", return_value=mock_session_ctx),
        ):
            await hil_router_edge(state)

        call_args = mock_repo.create.call_args[0][0]
        # lc_checkpoint_id is derived from workflow_id when no real checkpoint saver
        assert call_args.lc_checkpoint_id is not None
        assert len(call_args.lc_checkpoint_id) > 0


@pytest.mark.asyncio
class TestComputeScheduledSendAt:
    """Tests for the scheduled_send_at derivation logic."""

    async def test_scheduled_send_at_morning_brief_is_0545(self) -> None:
        """Morning Brief scheduled send is 05:45 UTC (nearest future occurrence)."""
        state = _make_state(requires_hil=True, workflow_type=WorkflowType.MORNING_BRIEF)
        now = _utcnow()

        result = compute_scheduled_send_at(state.workflow_type, now)

        # Should be 05:45 on some day (today or tomorrow)
        assert result.hour == 5
        assert result.minute == 45
        assert result > now

    async def test_scheduled_send_at_on_demand_is_now_plus_10_min(self) -> None:
        """On-Demand workflow deadline is now + 10 minutes."""
        state = _make_state(requires_hil=True, workflow_type=WorkflowType.ON_DEMAND)
        now = _utcnow()

        result = compute_scheduled_send_at(state.workflow_type, now)

        delta = result - now
        # Allow ±5 seconds tolerance
        assert timedelta(minutes=9, seconds=55) <= delta <= timedelta(minutes=10, seconds=5)

    async def test_scheduled_send_at_event_deep_dive_is_now_plus_30_min(self) -> None:
        """Event Deep Dive deadline is now + 30 minutes."""
        state = _make_state(requires_hil=True, workflow_type=WorkflowType.EVENT_DEEP_DIVE)
        now = _utcnow()

        result = compute_scheduled_send_at(state.workflow_type, now)

        delta = result - now
        assert timedelta(minutes=29, seconds=55) <= delta <= timedelta(minutes=30, seconds=5)

    async def test_scheduled_send_at_watchlist_is_1745(self) -> None:
        """Watchlist Scan scheduled send is 17:45 UTC."""
        state = _make_state(requires_hil=True, workflow_type=WorkflowType.WATCHLIST_SCAN)
        now = _utcnow()

        result = compute_scheduled_send_at(state.workflow_type, now)

        assert result.hour == 17
        assert result.minute == 45
        assert result > now
