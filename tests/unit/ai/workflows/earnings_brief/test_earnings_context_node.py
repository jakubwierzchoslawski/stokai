"""
Unit tests for earnings_context_node AgentNode.

TDD — PLAN-F-009 TASK-005.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import (
    OutputSchemaError,
    earnings_context_node,
)
from src.ai.workflows.earnings_brief.state import EarningsBriefState, ScenarioTree
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
        "bull": {
            "probability": 0.30,
            "rationale": "Strong guidance",
            "macro_drivers": ["low rates"],
            "sector_drivers": ["growth"],
            "implied_price_impact_pct": 5.0,
        },
        "base": {
            "probability": 0.50,
            "rationale": "In-line",
            "macro_drivers": ["stable inflation"],
            "sector_drivers": ["average"],
            "implied_price_impact_pct": 0.5,
        },
        "bear": {
            "probability": 0.20,
            "rationale": "Margin risk",
            "macro_drivers": ["cost pressure"],
            "sector_drivers": ["competition"],
            "implied_price_impact_pct": -4.0,
        },
        "analogies": [],
        "macro_summary": "Stable macro",
        "sector_summary": "Mixed sector",
    },
    "confidence": 0.80,
    "cost_usd": 0.25,
    "input_tokens": 800,
    "output_tokens": 400,
}


class TestEarningsContextNode:
    @pytest.mark.asyncio
    async def test_populates_scenario_tree(self):
        """Mock agent returns valid fixture; state.scenario_tree is a ScenarioTree."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.earnings_context_node"
            "._invoke_earnings_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await earnings_context_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.scenario_tree is not None
        assert isinstance(result.scenario_tree, ScenarioTree)

    @pytest.mark.asyncio
    async def test_scenarios_have_required_fields(self):
        """bull, base, bear each have probability and rationale."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.earnings_context_node"
            "._invoke_earnings_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await earnings_context_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.scenario_tree.bull.probability == 0.30
        assert result.scenario_tree.bull.rationale == "Strong guidance"
        assert result.scenario_tree.bear.probability == 0.20

    @pytest.mark.asyncio
    async def test_accumulates_cost(self):
        """Mock returns cost_usd=0.25; state.cost_usd increases."""
        state = _make_state(cost_usd=0.10)
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.earnings_context_node"
            "._invoke_earnings_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await earnings_context_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.cost_usd == pytest.approx(0.35)

    @pytest.mark.asyncio
    async def test_records_confidence_score(self):
        """state.confidence_scores["earnings_context_agent"] is set."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.earnings_context_node"
            "._invoke_earnings_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await earnings_context_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert "earnings_context_agent" in result.confidence_scores
        assert result.confidence_scores["earnings_context_agent"] == 0.80

    @pytest.mark.asyncio
    async def test_invalid_output_raises(self):
        """Mock returns dict missing 'bear'; OutputSchemaError propagates."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        bad_output = {
            "output": {
                "bull": _VALID_OUTPUT["output"]["bull"],
                "base": _VALID_OUTPUT["output"]["base"],
                # missing "bear"
                "analogies": [],
                "macro_summary": "ok",
                "sector_summary": "ok",
            },
            "confidence": 0.80,
            "cost_usd": 0.0,
        }

        with patch(
            "src.ai.workflows.earnings_brief.nodes.earnings_context_node"
            "._invoke_earnings_context_agent",
            AsyncMock(return_value=bad_output),
        ):
            with pytest.raises(OutputSchemaError):
                await earnings_context_node(
                    state, registry=registry, cost_guard=cost_guard
                )

    @pytest.mark.asyncio
    async def test_calls_cost_guard(self):
        """CostCeilingGuard.check is called."""
        state = _make_state(cost_usd=1.50)  # already at ceiling
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.earnings_context_node"
            "._invoke_earnings_context_agent",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            with pytest.raises(WorkflowCostLimitError):
                await earnings_context_node(
                    state, registry=registry, cost_guard=cost_guard
                )
