"""
Unit tests for recommendation_node AgentNode.

TDD — PLAN-F-009 TASK-006.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import OutputSchemaError
from src.ai.workflows.earnings_brief.nodes.recommendation_node import recommendation_node
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


_VALID_OUTPUT = {
    "output": {
        "bull": {"hold_signal": "BUY_MORE", "position_sizing_guidance": "+10%", "key_risk_factors": []},
        "base": {"hold_signal": "HOLD", "position_sizing_guidance": "0%", "key_risk_factors": []},
        "bear": {"hold_signal": "REDUCE", "position_sizing_guidance": "-15%", "key_risk_factors": []},
        "summary": "Monitor closely",
    },
    "confidence": 0.80,
    "cost_usd": 0.12,
    "input_tokens": 600,
    "output_tokens": 250,
}


class TestRecommendationNode:
    @pytest.mark.asyncio
    async def test_populates_correct_state_field(self):
        """Mock agent returns fixture; state.recommendation is set."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.recommendation_node"
            "._invoke_recommendation_synthesizer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await recommendation_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.recommendation is not None

    @pytest.mark.asyncio
    async def test_output_includes_all_three_scenarios(self):
        """recommendation output has bull, base, bear keys."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.recommendation_node"
            "._invoke_recommendation_synthesizer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await recommendation_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert "bull" in result.recommendation
        assert "base" in result.recommendation
        assert "bear" in result.recommendation

    @pytest.mark.asyncio
    async def test_accumulates_cost(self):
        state = _make_state(cost_usd=0.05)
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.recommendation_node"
            "._invoke_recommendation_synthesizer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await recommendation_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.cost_usd == pytest.approx(0.17)

    @pytest.mark.asyncio
    async def test_records_confidence_score(self):
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.recommendation_node"
            "._invoke_recommendation_synthesizer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await recommendation_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert "recommendation_synthesizer" in result.confidence_scores

    @pytest.mark.asyncio
    async def test_raises_on_missing_scenario(self):
        """Output missing 'bear' key raises OutputSchemaError."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        bad_output = {
            "output": {
                "bull": {"hold_signal": "BUY_MORE", "position_sizing_guidance": "+10%", "key_risk_factors": []},
                "base": {"hold_signal": "HOLD", "position_sizing_guidance": "0%", "key_risk_factors": []},
                # missing bear
            },
            "confidence": 0.80,
            "cost_usd": 0.0,
        }

        with patch(
            "src.ai.workflows.earnings_brief.nodes.recommendation_node"
            "._invoke_recommendation_synthesizer",
            AsyncMock(return_value=bad_output),
        ):
            with pytest.raises(OutputSchemaError):
                await recommendation_node(
                    state, registry=registry, cost_guard=cost_guard
                )
