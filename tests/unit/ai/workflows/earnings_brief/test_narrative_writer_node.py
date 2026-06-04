"""
Unit tests for narrative_writer_node AgentNode.

TDD — PLAN-F-009 TASK-006.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import OutputSchemaError
from src.ai.workflows.earnings_brief.nodes.narrative_writer_node import narrative_writer_node
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
        "title": "Earnings Risk Brief: Q2 2026",
        "sections": ["executive_summary", "scenario_tree", "recommendation"],
        "text": "ACME Corp is expected to report Q2 2026 results in line with analyst expectations...",
    },
    "confidence": 0.82,
    "cost_usd": 0.08,
    "input_tokens": 800,
    "output_tokens": 400,
}


class TestNarrativeWriterNode:
    @pytest.mark.asyncio
    async def test_populates_correct_state_field(self):
        """Mock agent returns fixture; state.report is set."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.narrative_writer_node"
            "._invoke_narrative_writer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await narrative_writer_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.report is not None
        assert isinstance(result.report, dict)

    @pytest.mark.asyncio
    async def test_report_is_nonempty_string(self):
        """state.report['text'] is non-empty."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.narrative_writer_node"
            "._invoke_narrative_writer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await narrative_writer_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.report["text"]
        assert len(result.report["text"]) > 0

    @pytest.mark.asyncio
    async def test_accumulates_cost(self):
        state = _make_state(cost_usd=0.30)
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.narrative_writer_node"
            "._invoke_narrative_writer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await narrative_writer_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert result.cost_usd == pytest.approx(0.38)

    @pytest.mark.asyncio
    async def test_records_confidence_score(self):
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        with patch(
            "src.ai.workflows.earnings_brief.nodes.narrative_writer_node"
            "._invoke_narrative_writer",
            AsyncMock(return_value=_VALID_OUTPUT),
        ):
            result = await narrative_writer_node(
                state, registry=registry, cost_guard=cost_guard
            )

        assert "narrative_writer" in result.confidence_scores

    @pytest.mark.asyncio
    async def test_raises_on_empty_text(self):
        """Output with empty 'text' raises OutputSchemaError."""
        state = _make_state()
        registry = MagicMock()
        cost_guard = CostCeilingGuard(ceiling_usd=1.50)

        bad_output = {
            "output": {"title": "x", "sections": [], "text": ""},
            "confidence": 0.80,
            "cost_usd": 0.0,
        }

        with patch(
            "src.ai.workflows.earnings_brief.nodes.narrative_writer_node"
            "._invoke_narrative_writer",
            AsyncMock(return_value=bad_output),
        ):
            with pytest.raises(OutputSchemaError):
                await narrative_writer_node(
                    state, registry=registry, cost_guard=cost_guard
                )
