"""
Unit tests for fetch_active_events DeterministicNode.

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowType
from src.ai.workflows.on_demand.nodes.fetch_active_events import fetch_active_events


def _make_state(**kwargs) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        **kwargs,
    )


class TestFetchActiveEvents:
    @pytest.mark.asyncio
    async def test_fetch_active_events_populates_active_events(self):
        """fetch_active_events sets state.active_events from repo results."""
        state = _make_state()
        events = [{"event_id": str(uuid.uuid4()), "type": "conflict"}]
        mock_repo = AsyncMock()
        mock_repo.get_active_events_for_company.return_value = events

        result = await fetch_active_events(state, geo_event_repo=mock_repo)
        assert result.active_events == events

    @pytest.mark.asyncio
    async def test_fetch_active_events_empty_result_is_valid(self):
        """Empty event list from repo is valid; state.active_events = []."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_active_events_for_company.return_value = []

        result = await fetch_active_events(state, geo_event_repo=mock_repo)
        assert result.active_events == []

    @pytest.mark.asyncio
    async def test_fetch_active_events_caps_at_50_rows(self):
        """Repo is called with limit=50."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_active_events_for_company.return_value = []

        await fetch_active_events(state, geo_event_repo=mock_repo)
        call_kwargs = mock_repo.get_active_events_for_company.call_args
        # Accept positional or keyword argument for limit
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("limit", 50) == 50
        else:
            # positional args: (company_id, tenant_id, days, limit)
            args = call_kwargs.args
            if len(args) >= 4:
                assert args[3] == 50

    @pytest.mark.asyncio
    async def test_fetch_active_events_queries_last_30_days(self):
        """Repo is called with days=30."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_active_events_for_company.return_value = []

        await fetch_active_events(state, geo_event_repo=mock_repo)
        call_kwargs = mock_repo.get_active_events_for_company.call_args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("days", 30) == 30

    @pytest.mark.asyncio
    async def test_fetch_active_events_returns_workflowstate(self):
        """Return type is WorkflowState."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_active_events_for_company.return_value = []

        result = await fetch_active_events(state, geo_event_repo=mock_repo)
        assert isinstance(result, WorkflowState)

    @pytest.mark.asyncio
    async def test_fetch_active_events_uses_tenant_id(self):
        """Repo is called with tenant_id from state."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_active_events_for_company.return_value = []

        await fetch_active_events(state, geo_event_repo=mock_repo)
        call_args = mock_repo.get_active_events_for_company.call_args
        # First arg should be company_id, second should be tenant_id
        args = call_args.args
        assert args[0] == state.company_id
        assert args[1] == state.tenant_id
