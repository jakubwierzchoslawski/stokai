"""
Unit tests for WatchlistScanWorkflow LangGraph graph.

TDD: written before implementation — PLAN-F-008 TASK-005.

Tests:
  - High/medium/low confidence routes correctly via route_after_quality
  - All nodes registered in the _NODE_SEQUENCE
  - WorkflowStructureValidator passes (evaluate_quality → narrative_writer tail)
  - Graph ainvoke() completes without error for each routing path
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.watchlist_scan_state import WatchlistScanState, route_after_quality
from src.ai.workflows.watchlist_scan_workflow import _NODE_SEQUENCE, WatchlistScanWorkflow


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


def _make_mock_agent(
    relevant_events=None,
    anomalies=None,
    high_anomaly_company_ids=None,
    recommendations=None,
    overall_confidence=0.80,
    report=None,
    cost_usd=0.01,
) -> MagicMock:
    """Build a mock agent whose invoke() returns structured output."""
    output = MagicMock()
    output.cost_usd = cost_usd
    output.confidence = overall_confidence
    output.relevant_events = relevant_events or []
    output.anomalies = anomalies or []
    output.high_anomaly_company_ids = high_anomaly_company_ids or []
    output.recommendations = recommendations or []
    output.overall_confidence = overall_confidence
    output.report = report or {"sections": ["overview"]}

    agent = MagicMock()
    agent.invoke = MagicMock(return_value=output)
    return agent


def _make_workflow(overall_confidence: float = 0.80) -> tuple[WatchlistScanWorkflow, Any]:
    """Build a WatchlistScanWorkflow with all deps mocked."""
    watchlist_repo = AsyncMock()
    watchlist_repo.list_company_ids = AsyncMock(return_value=[uuid.uuid4()])

    portfolio_repo = AsyncMock()
    portfolio_repo.list_company_ids = AsyncMock(return_value=[uuid.uuid4()])

    geo_event_repo = AsyncMock()
    geo_event_repo.list_for_companies = AsyncMock(return_value=[])

    score_repo = AsyncMock()
    score_repo.list_score_changes = AsyncMock(return_value=[])

    analogy_repo = AsyncMock()
    analogy_repo.get_analogies_for_events = AsyncMock(return_value={})

    hil_repo = AsyncMock()
    hil_repo.create = AsyncMock(return_value=MagicMock())

    brief_repo = AsyncMock()
    mock_brief_row = MagicMock()
    mock_brief_row.brief_id = uuid.uuid4()
    brief_repo.insert_memo = AsyncMock(return_value=mock_brief_row)

    email_service = AsyncMock()
    email_service.send_watchlist_scan = AsyncMock()

    filter_agent = _make_mock_agent(relevant_events=[])
    anomaly_agent = _make_mock_agent(anomalies=[], high_anomaly_company_ids=[])
    analyst_agent = _make_mock_agent(
        recommendations=[], overall_confidence=overall_confidence
    )
    writer_agent = _make_mock_agent(report={"sections": ["overview"]})

    judge_result = MagicMock()
    judge_result.confidence = overall_confidence
    tier1_judge = AsyncMock()
    tier1_judge.evaluate = AsyncMock(return_value=judge_result)

    workflow = WatchlistScanWorkflow(
        watchlist_repo=watchlist_repo,
        portfolio_repo=portfolio_repo,
        geo_event_repo=geo_event_repo,
        score_repo=score_repo,
        analogy_repo=analogy_repo,
        hil_repo=hil_repo,
        brief_repo=brief_repo,
        email_service=email_service,
        filter_agent=filter_agent,
        anomaly_agent=anomaly_agent,
        analyst_agent=analyst_agent,
        writer_agent=writer_agent,
        tier1_judge=tier1_judge,
        cost_ceiling_usd=1.00,
    )

    return workflow, {
        "brief_repo": brief_repo,
        "email_service": email_service,
        "hil_repo": hil_repo,
    }


# ── WorkflowStructureValidator ────────────────────────────────────────────────


class TestWorkflowStructureValidator:
    def test_node_sequence_ends_with_evaluate_quality_and_narrative_writer(self):
        """_NODE_SEQUENCE must end with ['evaluate_quality', 'narrative_writer']."""
        assert _NODE_SEQUENCE[-2] == "evaluate_quality"
        assert _NODE_SEQUENCE[-1] == "narrative_writer"

    def test_workflow_constructor_validates_structure(self):
        """WatchlistScanWorkflow constructor must validate structure (AC-004)."""
        # If construction succeeds, the validator passed
        workflow, _ = _make_workflow()
        assert workflow is not None

    def test_all_required_nodes_registered(self):
        """All expected nodes must appear in _NODE_SEQUENCE."""
        required = [
            "fetch_scoped_companies",
            "fetch_today_events",
            "fetch_score_changes",
            "filter_relevant_events",
            "detect_anomalies",
            "fetch_analogies",
            "run_watchlist_analyst",
            "evaluate_quality",
            "narrative_writer",
        ]
        for node in required:
            assert node in _NODE_SEQUENCE, f"Node '{node}' missing from _NODE_SEQUENCE"


# ── Routing ───────────────────────────────────────────────────────────────────


class TestRoutingAfterQuality:
    def test_high_confidence_routes_to_dispatch(self):
        """overall_confidence >= 0.70 → dispatch."""
        state = _make_state(overall_confidence=0.80)
        assert route_after_quality(state) == "dispatch"

    def test_medium_confidence_routes_to_hil_enqueue(self):
        """overall_confidence in [0.40, 0.70) → hil_enqueue."""
        state = _make_state(overall_confidence=0.55)
        assert route_after_quality(state) == "hil_enqueue"

    def test_low_confidence_routes_to_block_and_notify(self):
        """overall_confidence < 0.40 → block_and_notify."""
        state = _make_state(overall_confidence=0.20)
        assert route_after_quality(state) == "block_and_notify"


# ── Graph ainvoke ─────────────────────────────────────────────────────────────


class TestWatchlistScanWorkflowAinvoke:
    @pytest.mark.asyncio
    async def test_high_confidence_ainvoke_calls_dispatch(self):
        """ainvoke with high confidence must call brief_repo.insert_memo."""
        workflow, mocks = _make_workflow(overall_confidence=0.85)
        state = _make_state()

        await workflow.ainvoke(state)

        mocks["brief_repo"].insert_memo.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_confidence_ainvoke_calls_email(self):
        """ainvoke with high confidence must call email_service.send_watchlist_scan."""
        workflow, mocks = _make_workflow(overall_confidence=0.85)
        state = _make_state()

        await workflow.ainvoke(state)

        mocks["email_service"].send_watchlist_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_medium_confidence_ainvoke_enqueues_hil(self):
        """ainvoke with medium confidence must call hil_repo.create."""
        workflow, mocks = _make_workflow(overall_confidence=0.55)
        state = _make_state()

        await workflow.ainvoke(state)

        mocks["hil_repo"].create.assert_called_once()

    @pytest.mark.asyncio
    async def test_medium_confidence_ainvoke_does_not_send_email(self):
        """ainvoke with medium confidence must NOT send email."""
        workflow, mocks = _make_workflow(overall_confidence=0.55)
        state = _make_state()

        await workflow.ainvoke(state)

        mocks["email_service"].send_watchlist_scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_confidence_ainvoke_does_not_dispatch(self):
        """ainvoke with low confidence must NOT insert Brief or send email."""
        workflow, mocks = _make_workflow(overall_confidence=0.15)
        state = _make_state()

        await workflow.ainvoke(state)

        mocks["brief_repo"].insert_memo.assert_not_called()
        mocks["email_service"].send_watchlist_scan.assert_not_called()


# ── HIL Resume ───────────────────────────────────────────────────────────────


class TestHILResume:
    @pytest.mark.asyncio
    async def test_approval_routes_to_dispatch(self):
        """HIL approval must call brief_repo.insert_memo and email_service."""
        workflow, mocks = _make_workflow()
        state = _make_state(overall_confidence=0.55)

        await workflow.resume_from_hil(state, approved=True)

        mocks["brief_repo"].insert_memo.assert_called_once()
        mocks["email_service"].send_watchlist_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejection_routes_to_block_and_notify(self):
        """HIL rejection must NOT insert Brief or send email."""
        workflow, mocks = _make_workflow()
        state = _make_state(overall_confidence=0.55)

        result = await workflow.resume_from_hil(state, approved=False)

        mocks["brief_repo"].insert_memo.assert_not_called()
        mocks["email_service"].send_watchlist_scan.assert_not_called()
        assert result is not None
