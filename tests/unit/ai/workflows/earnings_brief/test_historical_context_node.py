"""
Unit tests for historical_context_node AgentNode.

TDD — PLAN-F-009 TASK-006.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.historical_context_node import (
    historical_context_node,
)
from src.ai.workflows.earnings_brief.state import EarningsBriefState
from src.ai.workflows.errors import WorkflowCostLimitError


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


_VALID_OUTPUT = {
    "output": {
        "analogies": [{"period": "2020-Q3", "company": "AAPL"}],
        "summary": "Similar patterns found in 2020",
        "insufficient_data": False,
    },
    "confidence": 0.75,
    "cost_usd": 0.10,
    "input_tokens": 500,
    "output_tokens": 200,
}


class TestHistoricalContextNode:
    @pytest.mark.asyncio
    async def test_populates_correct_state_field(self):
        """Mock agent returns fixture; state.analogies_output is set."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.historical_context_node"
            "._invoke_historical_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await historical_context_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.analogies_output is not None
        assert isinstance(result.analogies_output, dict)

    @pytest.mark.asyncio
    async def test_accumulates_cost(self):
        """Mock returns cost_usd=0.10; state.cost_usd increases."""
        state = _make_state(cost_usd=0.20)
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.historical_context_node"
            "._invoke_historical_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await historical_context_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.cost_usd == pytest.approx(0.30)

    @pytest.mark.asyncio
    async def test_records_confidence_score(self):
        """confidence_scores['historical_context_agent'] is set."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.historical_context_node"
            "._invoke_historical_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await historical_context_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert "historical_context_agent" in result.confidence_scores
        assert result.confidence_scores["historical_context_agent"] == 0.75
