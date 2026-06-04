"""
Unit tests for TASK-006: evaluate_quality_node injection into Mode B workflows.

TDD: written before the graph updates exist.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowType


def _make_state(**kwargs) -> WorkflowState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.ON_DEMAND,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "recommendation": {"signal": "BUY"},
        "confidence_scores": {"exposure": 0.8, "historical": 0.75},
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


# ── on_demand graph tests ─────────────────────────────────────────────────────


def test_on_demand_graph_node_sequence_contains_tier1_eval():
    """On-demand graph NODE_SEQUENCE must include 'tier1_eval'."""
    from src.ai.workflows.on_demand.graph import _NODE_SEQUENCE

    assert "tier1_eval" in _NODE_SEQUENCE


def test_on_demand_graph_tier1_eval_before_narrative_writer():
    """tier1_eval must appear immediately before narrative_writer in the sequence."""
    from src.ai.workflows.on_demand.graph import _NODE_SEQUENCE

    idx_eval = _NODE_SEQUENCE.index("tier1_eval")
    idx_narrative = _NODE_SEQUENCE.index("narrative_writer")
    # tier1_eval must come before narrative_writer
    assert idx_eval < idx_narrative


@pytest.mark.asyncio
async def test_on_demand_graph_runs_tier1_eval_with_mock():
    """Running on_demand graph with mocked judge updates confidence_scores."""
    from src.ai.workflows.on_demand.graph import _PipelineGraph

    registry = MagicMock()
    graph = _PipelineGraph(registry=registry, cost_ceiling_usd=10.0)

    state = _make_state()

    # Mock the tier1_judge_service that the graph injects
    mock_judge = AsyncMock()
    from src.ai.evaluation.schemas.evaluation_schemas import EvaluationResult

    eval_result = EvaluationResult(
        eval_id=uuid.uuid4(),
        run_id=state.workflow_id,
        eval_type="tier_1",
        judge_model="claude-opus-4-7",
        scores={"factual_grounding": 0.85},
        overall_quality=0.85,
        prompt_version="v1",
        evaluated_at=datetime.now(tz=timezone.utc),
    )
    mock_judge.evaluate_output = AsyncMock(return_value=eval_result)

    # Set tier1_judge on graph
    graph._tier1_judge = mock_judge

    config = MagicMock()
    config.configurable = {"company_repo": None, "geo_event_repo": None}

    # Patch all AgentNode calls to be no-ops
    from unittest.mock import patch

    async def _noop_node(s, **kwargs):
        return s

    with (
        patch(
            "src.ai.workflows.on_demand.graph.exposure_analyst_node",
            side_effect=_noop_node,
        ),
        patch(
            "src.ai.workflows.on_demand.graph.historical_context_node",
            side_effect=_noop_node,
        ),
        patch(
            "src.ai.workflows.on_demand.graph.anomaly_detector_node",
            side_effect=_noop_node,
        ),
        patch(
            "src.ai.workflows.on_demand.graph.recommendation_node",
            side_effect=_noop_node,
        ),
        patch(
            "src.ai.workflows.on_demand.graph.narrative_writer_node",
            side_effect=_noop_node,
        ),
    ):
        result = await graph.ainvoke(state, config=config)

    # tier1_eval should have been set in confidence_scores
    assert "tier1_eval" in result.confidence_scores


# ── morning_brief graph tests ─────────────────────────────────────────────────


def test_morning_brief_graph_node_sequence_contains_evaluate_quality():
    """Morning brief graph _NODE_SEQUENCE must include 'evaluate_quality'."""
    from src.ai.workflows.morning_brief.graph import _NODE_SEQUENCE

    assert "evaluate_quality" in _NODE_SEQUENCE


def test_morning_brief_graph_evaluate_quality_before_narrative_writer():
    """evaluate_quality must appear before narrative_writer in morning_brief sequence."""
    from src.ai.workflows.morning_brief.graph import _NODE_SEQUENCE

    idx_eval = _NODE_SEQUENCE.index("evaluate_quality")
    idx_narrative = _NODE_SEQUENCE.index("narrative_writer")
    assert idx_eval < idx_narrative


# ── watchlist_scan graph tests ────────────────────────────────────────────────


def test_watchlist_scan_graph_node_sequence_contains_evaluate_quality():
    """Watchlist scan graph _NODE_SEQUENCE must include 'evaluate_quality'."""
    from src.ai.workflows.watchlist_scan.graph import _NODE_SEQUENCE

    assert "evaluate_quality" in _NODE_SEQUENCE


def test_watchlist_scan_graph_evaluate_quality_before_narrative_writer():
    """evaluate_quality must appear before narrative_writer in watchlist_scan sequence."""
    from src.ai.workflows.watchlist_scan.graph import _NODE_SEQUENCE

    idx_eval = _NODE_SEQUENCE.index("evaluate_quality")
    idx_narrative = _NODE_SEQUENCE.index("narrative_writer")
    assert idx_eval < idx_narrative


# ── earnings_risk_brief graph tests ──────────────────────────────────────────


def test_earnings_risk_brief_graph_node_sequence_contains_evaluate_quality():
    """Earnings risk brief graph _NODE_SEQUENCE must include 'evaluate_quality'."""
    from src.ai.workflows.earnings_risk_brief.graph import _NODE_SEQUENCE

    assert "evaluate_quality" in _NODE_SEQUENCE


def test_earnings_risk_brief_graph_evaluate_quality_before_narrative_writer():
    """evaluate_quality must appear before narrative_writer in earnings_risk_brief sequence."""
    from src.ai.workflows.earnings_risk_brief.graph import _NODE_SEQUENCE

    idx_eval = _NODE_SEQUENCE.index("evaluate_quality")
    idx_narrative = _NODE_SEQUENCE.index("narrative_writer")
    assert idx_eval < idx_narrative


# ── event_deep_dive graph tests ───────────────────────────────────────────────


def test_event_deep_dive_graph_node_sequence_contains_evaluate_quality():
    """Event deep dive graph _NODE_SEQUENCE must include 'evaluate_quality'."""
    from src.ai.workflows.event_deep_dive.graph import _NODE_SEQUENCE

    assert "evaluate_quality" in _NODE_SEQUENCE
