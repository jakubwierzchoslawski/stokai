"""
Unit tests for MemoStore (PLAN-F-010 TASK-009).

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import (
    BriefCreate,
    DeepDiveWorkflowState,
    GeoEvent,
    MemoDraft,
)
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
        "event_full": GeoEvent(event_id=event_id, title="Test Event"),
        "memo_draft": MemoDraft(
            headline="Test Headline",
            executive_summary="Test summary",
            event_analysis={"key": "value"},
            market_impact={"impact": "low"},
            confidence=0.80,
        ),
        "cost_usd": 0.25,
        "confidence_scores": {"workflow": 0.80},
        "langfuse_trace_id": "trace-abc-123",
    }
    defaults.update(kwargs)
    return DeepDiveWorkflowState(**defaults)


def _make_brief_orm(brief_id: uuid.UUID, event_id: uuid.UUID) -> MagicMock:
    orm = MagicMock()
    orm.brief_id = brief_id
    orm.event_id = event_id
    return orm


class TestMemoStorePersist:
    @pytest.mark.asyncio
    async def test_persist_returns_brief_with_id(self):
        """persist() returns a Brief ORM row with a populated brief_id."""
        from src.ai.workflows.shared.memo_store import MemoStore

        state = _make_state()
        expected_brief_id = uuid.uuid4()
        event_id = state.event_full.event_id

        workflow_run_repo = AsyncMock()
        workflow_run_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_orm = _make_brief_orm(expected_brief_id, event_id)
        brief_repo.insert_memo = AsyncMock(return_value=brief_orm)

        store = MemoStore()
        result = await store.persist(
            state=state,
            workflow_run_repo=workflow_run_repo,
            brief_repo=brief_repo,
            confidence=0.80,
            cost_limited=False,
        )

        assert result is not None
        assert result.brief_id == expected_brief_id

    @pytest.mark.asyncio
    async def test_persist_calls_insert_memo_with_correct_event_id(self):
        """persist() calls brief_repo.insert_memo with state.event_full.event_id."""
        from src.ai.workflows.shared.memo_store import MemoStore

        state = _make_state()
        event_id = state.event_full.event_id
        expected_brief_id = uuid.uuid4()

        workflow_run_repo = AsyncMock()
        workflow_run_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_orm = _make_brief_orm(expected_brief_id, event_id)
        brief_repo.insert_memo = AsyncMock(return_value=brief_orm)

        store = MemoStore()
        await store.persist(
            state=state,
            workflow_run_repo=workflow_run_repo,
            brief_repo=brief_repo,
            confidence=0.80,
            cost_limited=False,
        )

        brief_repo.insert_memo.assert_called_once()
        call_arg: BriefCreate = brief_repo.insert_memo.call_args[0][0]
        assert call_arg.event_id == event_id
        assert call_arg.tenant_id == state.tenant_id
        assert call_arg.confidence == pytest.approx(0.80)
        assert call_arg.cost_limited is False

    @pytest.mark.asyncio
    async def test_persist_calls_update_status_on_workflow_run(self):
        """persist() calls workflow_run_repo.update_status after inserting the brief."""
        from src.ai.workflows.shared.memo_store import MemoStore

        state = _make_state()
        expected_brief_id = uuid.uuid4()
        event_id = state.event_full.event_id

        workflow_run_repo = AsyncMock()
        workflow_run_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_orm = _make_brief_orm(expected_brief_id, event_id)
        brief_repo.insert_memo = AsyncMock(return_value=brief_orm)

        store = MemoStore()
        await store.persist(
            state=state,
            workflow_run_repo=workflow_run_repo,
            brief_repo=brief_repo,
            confidence=0.80,
            cost_limited=False,
        )

        workflow_run_repo.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_with_cost_limited_sets_flag(self):
        """persist() with cost_limited=True sets BriefCreate.cost_limited=True."""
        from src.ai.workflows.shared.memo_store import MemoStore

        state = _make_state()
        expected_brief_id = uuid.uuid4()
        event_id = state.event_full.event_id

        workflow_run_repo = AsyncMock()
        workflow_run_repo.update_status = AsyncMock()

        brief_repo = AsyncMock()
        brief_orm = _make_brief_orm(expected_brief_id, event_id)
        brief_repo.insert_memo = AsyncMock(return_value=brief_orm)

        store = MemoStore()
        await store.persist(
            state=state,
            workflow_run_repo=workflow_run_repo,
            brief_repo=brief_repo,
            confidence=0.30,
            cost_limited=True,
        )

        brief_repo.insert_memo.assert_called_once()
        call_arg: BriefCreate = brief_repo.insert_memo.call_args[0][0]
        assert call_arg.cost_limited is True
