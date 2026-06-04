"""
Unit tests for fetch_sector_recent_earnings DeterministicNode.

TDD — PLAN-F-009 TASK-004.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.earnings_brief.nodes.context import NodeContext
from src.ai.workflows.earnings_brief.nodes.fetch_sector_recent_earnings import (
    fetch_sector_recent_earnings,
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


def _make_peer(n: int) -> MagicMock:
    m = MagicMock()
    m.model_dump.return_value = {"peer_id": str(uuid.uuid4()), "n": n}
    return m


class TestFetchSectorRecentEarnings:
    @pytest.mark.asyncio
    async def test_populates_state(self):
        """Mock returns peers; state.sector_recent_earnings updated."""
        state = _make_state()
        peers = [_make_peer(i) for i in range(5)]
        repo = AsyncMock()
        repo.list_sector_recent = AsyncMock(return_value=peers)
        ctx = NodeContext(earnings_repo=repo)

        result = await fetch_sector_recent_earnings(state, ctx)

        assert len(result.sector_recent_earnings) == 5

    @pytest.mark.asyncio
    async def test_caps_at_twenty(self):
        """25 rows returned; node trims to 20."""
        state = _make_state()
        peers = [_make_peer(i) for i in range(25)]
        repo = AsyncMock()
        repo.list_sector_recent = AsyncMock(return_value=peers)
        ctx = NodeContext(earnings_repo=repo)

        result = await fetch_sector_recent_earnings(state, ctx)

        assert len(result.sector_recent_earnings) == 20

    @pytest.mark.asyncio
    async def test_no_repo_returns_empty(self):
        """Without earnings_repo, returns empty list."""
        state = _make_state()
        ctx = NodeContext()

        result = await fetch_sector_recent_earnings(state, ctx)

        assert result.sector_recent_earnings == []
