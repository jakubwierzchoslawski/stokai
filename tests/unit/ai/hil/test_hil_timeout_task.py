"""
Unit tests for expire_overdue_hil_items Celery task.

All repository and service calls are mocked. No real DB or Celery worker required.

TDD tests defined before implementation (PLAN-F-013 TASK-006).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.hil.hil_timeout_task import _run_expire_overdue_hil_items


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_overdue_item(item_id: uuid.UUID | None = None) -> MagicMock:
    item = MagicMock()
    item.item_id = item_id or uuid.uuid4()
    item.workflow_run_id = uuid.uuid4()
    item.tenant_id = uuid.uuid4()
    item.lc_checkpoint_id = f"hil:{uuid.uuid4()}"
    item.status = "pending"
    item.scheduled_send_at = _utcnow() - timedelta(hours=2)
    return item


@pytest.mark.asyncio
class TestExpireOverdueHilItems:
    """Tests for the async core of the expire_overdue_hil_items task."""

    async def test_no_items_no_action(self) -> None:
        """When no items are overdue, no action service calls are made."""
        mock_hil_repo = AsyncMock()
        mock_hil_repo.list_timed_out_pending = AsyncMock(return_value=[])

        mock_action_service = AsyncMock()

        await _run_expire_overdue_hil_items(
            hil_repo=mock_hil_repo,
            action_service=mock_action_service,
        )

        mock_action_service.apply_action.assert_not_called()

    async def test_overdue_item_is_terminated_and_marked_timed_out(self) -> None:
        """Overdue item is rejected by system reviewer and then marked timed_out."""
        mock_hil_repo = AsyncMock()
        overdue_item = _make_overdue_item()
        mock_hil_repo.list_timed_out_pending = AsyncMock(return_value=[overdue_item])
        mock_hil_repo.update_status = AsyncMock()

        action_result = MagicMock()
        action_result.feedback_id = uuid.uuid4()
        mock_action_service = AsyncMock()
        mock_action_service.apply_action = AsyncMock(return_value=action_result)

        await _run_expire_overdue_hil_items(
            hil_repo=mock_hil_repo,
            action_service=mock_action_service,
        )

        # apply_action should be called with action='reject'
        mock_action_service.apply_action.assert_called_once()
        call_kwargs = mock_action_service.apply_action.call_args[1]
        assert call_kwargs.get("action") == "reject"
        assert call_kwargs.get("item_id") == overdue_item.item_id

        # Status should then be updated to timed_out
        mock_hil_repo.update_status.assert_called_once()
        update_kwargs = mock_hil_repo.update_status.call_args[1]
        from src.storage.repositories.hil_queue_repository import HILStatus
        assert update_kwargs.get("status") == HILStatus.TIMED_OUT

    async def test_episodic_audit_row_written_on_timeout(self) -> None:
        """Workflow run repository records hil_timeout audit event."""
        mock_hil_repo = AsyncMock()
        overdue_item = _make_overdue_item()
        mock_hil_repo.list_timed_out_pending = AsyncMock(return_value=[overdue_item])
        mock_hil_repo.update_status = AsyncMock()

        action_result = MagicMock()
        action_result.feedback_id = uuid.uuid4()
        mock_action_service = AsyncMock()
        mock_action_service.apply_action = AsyncMock(return_value=action_result)
        mock_workflow_run_repo = AsyncMock()

        await _run_expire_overdue_hil_items(
            hil_repo=mock_hil_repo,
            action_service=mock_action_service,
            workflow_run_repo=mock_workflow_run_repo,
        )

        # Audit row via append_audit_event (or update_status as fallback)
        assert (
            mock_workflow_run_repo.append_audit_event.called
            or mock_workflow_run_repo.update_status.called
        )

    async def test_non_overdue_pending_items_are_not_touched(self) -> None:
        """Items whose deadline is in the future are not processed."""
        mock_hil_repo = AsyncMock()
        # list_timed_out_pending returns empty (no past-deadline items)
        mock_hil_repo.list_timed_out_pending = AsyncMock(return_value=[])

        mock_action_service = AsyncMock()

        await _run_expire_overdue_hil_items(
            hil_repo=mock_hil_repo,
            action_service=mock_action_service,
        )

        mock_action_service.apply_action.assert_not_called()
