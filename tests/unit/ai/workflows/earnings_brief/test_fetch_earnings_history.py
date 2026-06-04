"""
Unit tests for fetch_earnings_history DeterministicNode.

TDD — PLAN-F-009 TASK-004.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.earnings_brief.nodes.context import NodeContext
from src.ai.workflows.earnings_brief.nodes.fetch_earnings_history import (
    fetch_earnings_history,
)
from src.ai.workflows.earnings_brief.state import EarningsBriefState


def _make_state(**kwargs) -> EarningsBriefState:
    defaults = dict(
        workflow_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        earnings_date=date.today(),
        started_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kwargs)
    return EarningsBriefState(**defaults)


class TestFetchEarningsHistory:
    @pytest.mark.asyncio
    async def test_populates_state(self):
        """Mock returns 5 records; state.earnings_history has 5 items."""
        state = _make_state()
        records = [
            MagicMock(**{"model_dump.return_value": {"event_id": str(uuid.uuid4()), "i": i}})
            for i in range(5)
        ]
        repo = AsyncMock()
        repo.list_history = AsyncMock(return_value=records)
        ctx = NodeContext(earnings_repo=repo)

        result = await fetch_earnings_history(state, ctx)

        assert len(result.earnings_history) == 5

    @pytest.mark.asyncio
    async def test_empty_is_not_error(self):
        """Repository returns []; node succeeds with empty history."""
        state = _make_state()
        repo = AsyncMock()
        repo.list_history = AsyncMock(return_value=[])
        ctx = NodeContext(earnings_repo=repo)

        result = await fetch_earnings_history(state, ctx)

        assert result.earnings_history == []

    @pytest.mark.asyncio
    async def test_no_repo_returns_empty(self):
        """Without earnings_repo, returns empty history."""
        state = _make_state()
        ctx = NodeContext()

        result = await fetch_earnings_history(state, ctx)

        assert result.earnings_history == []

    @pytest.mark.asyncio
    async def test_scoped_to_tenant(self):
        """Asserts repository called with tenant_id."""
        state = _make_state()
        repo = AsyncMock()
        repo.list_history = AsyncMock(return_value=[])
        ctx = NodeContext(earnings_repo=repo)

        await fetch_earnings_history(state, ctx)

        repo.list_history.assert_called_once_with(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
            limit=8,
        )
