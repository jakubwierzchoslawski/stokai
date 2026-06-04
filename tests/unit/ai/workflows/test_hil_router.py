"""
Unit tests for HILRouter (PLAN-F-010 TASK-012).

Tests the src.ai.workflows.shared.hil_router module.
All external deps (HILQueueRepository, DB) are mocked.
TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState, GeoEvent
from src.ai.workflows.state import WorkflowStatus, WorkflowType


def _make_state(**kwargs) -> DeepDiveWorkflowState:
    event_id = uuid.uuid4()
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.EVENT_DEEP_DIVE,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "inputs": {"event_id": str(event_id)},
        "event_full": GeoEvent(event_id=event_id),
        "confidence_scores": {"workflow": 0.55},
        "requires_hil": True,
    }
    defaults.update(kwargs)
    return DeepDiveWorkflowState(**defaults)


class TestHILRouterEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_creates_hil_queue_item(self):
        """HILRouter.enqueue creates a HIL queue row."""
        from src.ai.workflows.shared.hil_router import HILRouter

        state = _make_state()

        mock_repo = AsyncMock()
        created_item = MagicMock()
        created_item.item_id = uuid.uuid4()
        mock_repo.create = AsyncMock(return_value=created_item)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        router = HILRouter()
        with (
            patch("src.ai.workflows.shared.hil_router.HILQueueRepository", return_value=mock_repo),
            patch("src.ai.workflows.shared.hil_router._get_db_session", return_value=mock_session_ctx),
        ):
            await router.enqueue(state)

        mock_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_sets_30_minute_deadline(self):
        """HILRouter.enqueue sets scheduled_send = now + 30 min for EVENT_DEEP_DIVE."""
        from src.ai.workflows.shared.hil_router import HILRouter

        state = _make_state(workflow_type=WorkflowType.EVENT_DEEP_DIVE)

        mock_repo = AsyncMock()
        created_item = MagicMock()
        created_item.item_id = uuid.uuid4()
        mock_repo.create = AsyncMock(return_value=created_item)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        router = HILRouter()
        now = datetime.now(tz=timezone.utc)
        with (
            patch("src.ai.workflows.shared.hil_router.HILQueueRepository", return_value=mock_repo),
            patch("src.ai.workflows.shared.hil_router._get_db_session", return_value=mock_session_ctx),
        ):
            await router.enqueue(state)

        call_arg = mock_repo.create.call_args[0][0]
        delta = call_arg.scheduled_send_at - now
        # Should be ~30 minutes ahead
        assert 25 * 60 <= delta.total_seconds() <= 35 * 60

    @pytest.mark.asyncio
    async def test_enqueue_stores_workflow_run_id_in_queue_item(self):
        """HILRouter.enqueue stores state.workflow_id in the queue item."""
        from src.ai.workflows.shared.hil_router import HILRouter

        state = _make_state()

        mock_repo = AsyncMock()
        created_item = MagicMock()
        created_item.item_id = uuid.uuid4()
        mock_repo.create = AsyncMock(return_value=created_item)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        router = HILRouter()
        with (
            patch("src.ai.workflows.shared.hil_router.HILQueueRepository", return_value=mock_repo),
            patch("src.ai.workflows.shared.hil_router._get_db_session", return_value=mock_session_ctx),
        ):
            await router.enqueue(state)

        call_arg = mock_repo.create.call_args[0][0]
        assert call_arg.workflow_run_id == state.workflow_id

    @pytest.mark.asyncio
    async def test_enqueue_with_missing_hil_queue_table_logs_warning(self):
        """HILRouter.enqueue gracefully handles missing hil_queue table."""
        from src.ai.workflows.shared.hil_router import HILRouter

        state = _make_state()

        mock_repo = AsyncMock()
        mock_repo.create = AsyncMock(side_effect=Exception("relation hil_queue does not exist"))

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        router = HILRouter()
        # Should not raise — logs warning and continues
        with (
            patch("src.ai.workflows.shared.hil_router.HILQueueRepository", return_value=mock_repo),
            patch("src.ai.workflows.shared.hil_router._get_db_session", return_value=mock_session_ctx),
            patch("src.ai.workflows.shared.hil_router.logger") as mock_logger,
        ):
            await router.enqueue(state)

        mock_logger.warning.assert_called_once()
