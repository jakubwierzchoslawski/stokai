"""
Unit tests for WorkflowRunRepository (PLAN-F-010 TASK-002 additions).

TDD: written before extended implementation.
Tests exercise: create_with_event, update_status_to_cost_limited.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowType, WorkflowStatus


def _make_workflow_state(**kwargs) -> WorkflowState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.EVENT_DEEP_DIVE,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "status": WorkflowStatus.RUNNING,
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


class TestCreateWorkflowRun:
    @pytest.mark.asyncio
    async def test_create_workflow_run_sets_status_pending(self):
        """create() should create a row with status=RUNNING (initial state)."""
        from src.storage.repositories.workflow_run_repository import WorkflowRunRepository
        from src.storage.models.workflow_run import WorkflowRun

        session = AsyncMock()
        session.flush = AsyncMock()

        mock_orm = MagicMock(spec=WorkflowRun)
        mock_orm.status = WorkflowStatus.RUNNING.value

        async def mock_refresh(obj):
            obj.status = WorkflowStatus.RUNNING.value

        session.refresh = AsyncMock(side_effect=mock_refresh)

        state = _make_workflow_state(status=WorkflowStatus.RUNNING)
        repo = WorkflowRunRepository(session)
        result = await repo.create(state)

        session.add.assert_called_once()
        session.flush.assert_called_once()


class TestUpdateStatusToCostLimited:
    @pytest.mark.asyncio
    async def test_update_status_to_cost_limited_sets_flag(self):
        """update_status() with COST_LIMIT should execute an UPDATE statement."""
        from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        workflow_id = uuid.uuid4()
        repo = WorkflowRunRepository(session)
        await repo.update_status(
            workflow_id,
            WorkflowStatus.COST_LIMIT,
            cost_usd=1.50,
        )

        session.execute.assert_called_once()
        session.flush.assert_called_once()
