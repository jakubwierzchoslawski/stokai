"""
Unit tests for fetch_macro_context DeterministicNode.

TDD — PLAN-F-009 TASK-004.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.earnings_brief.nodes.context import NodeContext
from src.ai.workflows.earnings_brief.nodes.fetch_macro_context import fetch_macro_context
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


def _make_indicator(n: int) -> MagicMock:
    m = MagicMock()
    m.model_dump.return_value = {"name": f"indicator_{n}", "value": n * 0.1}
    return m


class TestFetchMacroContext:
    @pytest.mark.asyncio
    async def test_populates_state(self):
        """Mock returns 10 indicators; state.macro_context set."""
        state = _make_state()
        indicators = [_make_indicator(i) for i in range(10)]
        repo = AsyncMock()
        repo.get_latest_indicators = AsyncMock(return_value=indicators)
        ctx = NodeContext(macro_repo=repo)

        result = await fetch_macro_context(state, ctx)

        assert result.macro_context is not None
        assert result.macro_context["indicator_count"] == 10

    @pytest.mark.asyncio
    async def test_caps_at_ten(self):
        """Repository returns 15 items; node trims to 10."""
        state = _make_state()
        indicators = [_make_indicator(i) for i in range(15)]
        repo = AsyncMock()
        repo.get_latest_indicators = AsyncMock(return_value=indicators)
        ctx = NodeContext(macro_repo=repo)

        result = await fetch_macro_context(state, ctx)

        assert result.macro_context["indicator_count"] == 10
        assert len(result.macro_context["indicators"]) == 10

    @pytest.mark.asyncio
    async def test_no_repo_returns_empty(self):
        """Without macro_repo, returns empty context."""
        state = _make_state()
        ctx = NodeContext()

        result = await fetch_macro_context(state, ctx)

        assert result.macro_context is not None
        assert result.macro_context["indicator_count"] == 0
