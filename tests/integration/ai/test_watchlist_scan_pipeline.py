"""
Integration tests for the end-to-end Watchlist Scan pipeline.

TDD: written before implementation — PLAN-F-008 TASK-012.

Tests:
  - End-to-end dispatch path with mocked AI agents
  - End-to-end HIL routing with mocked AI agents
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.watchlist_scan_state import WatchlistScanState
from src.ai.workflows.watchlist_scan_workflow import WatchlistScanWorkflow


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


def _make_agent(
    overall_confidence: float = 0.80,
    anomalies: list | None = None,
    high_anomaly_company_ids: list | None = None,
) -> MagicMock:
    """Build a mock agent with customizable output."""
    output = MagicMock()
    output.cost_usd = 0.05
    output.confidence = overall_confidence
    output.relevant_events = []
    output.anomalies = anomalies or []
    output.high_anomaly_company_ids = high_anomaly_company_ids or []
    output.recommendations = [{"action": "HOLD", "rationale": "stable"}]
    output.overall_confidence = overall_confidence
    output.report = {
        "headline": "Watchlist scan complete",
        "sections": ["overview", "anomalies", "recommendations"],
    }
    agent = MagicMock()
    agent.invoke = MagicMock(return_value=output)
    return agent


def _build_workflow(overall_confidence: float = 0.80) -> tuple[WatchlistScanWorkflow, dict]:
    """Build a fully wired workflow with mocked external deps."""
    watchlist_repo = AsyncMock()
    watchlist_repo.list_company_ids = AsyncMock(
        return_value=[uuid.uuid4(), uuid.uuid4()]
    )
    portfolio_repo = AsyncMock()
    portfolio_repo.list_company_ids = AsyncMock(
        return_value=[uuid.uuid4()]
    )
    geo_event_repo = AsyncMock()
    geo_event_repo.list_for_companies = AsyncMock(
        return_value=[
            {"event_id": str(uuid.uuid4()), "title": "Oil price spike", "severity": "medium"}
        ]
    )
    score_repo = AsyncMock()
    score_repo.list_score_changes = AsyncMock(
        return_value=[{"company_id": str(uuid.uuid4()), "delta": -3.5}]
    )
    analogy_repo = AsyncMock()
    analogy_repo.get_analogies_for_events = AsyncMock(return_value={})

    hil_repo = AsyncMock()
    hil_repo.create = AsyncMock(return_value=MagicMock())

    brief_repo = AsyncMock()
    mock_row = MagicMock()
    mock_row.brief_id = uuid.uuid4()
    brief_repo.insert_memo = AsyncMock(return_value=mock_row)

    email_service = AsyncMock()
    email_service.send_watchlist_scan = AsyncMock()

    filter_agent = _make_agent(overall_confidence=overall_confidence)
    anomaly_agent = _make_agent(overall_confidence=overall_confidence)
    analyst_agent = _make_agent(overall_confidence=overall_confidence)
    writer_agent = _make_agent(overall_confidence=overall_confidence)

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
        "watchlist_repo": watchlist_repo,
        "portfolio_repo": portfolio_repo,
        "score_repo": score_repo,
    }


class TestWatchlistScanEndToEndDispatch:
    @pytest.mark.asyncio
    async def test_full_pipeline_inserts_brief_on_high_confidence(self):
        """End-to-end: high confidence path inserts a Brief row."""
        workflow, mocks = _build_workflow(overall_confidence=0.85)
        state = _make_state()

        result = await workflow.ainvoke(state)

        mocks["brief_repo"].insert_memo.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_pipeline_sends_email_on_high_confidence(self):
        """End-to-end: high confidence path sends email."""
        workflow, mocks = _build_workflow(overall_confidence=0.85)
        state = _make_state()

        result = await workflow.ainvoke(state)

        mocks["email_service"].send_watchlist_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_pipeline_sets_brief_id_on_result_state(self):
        """End-to-end: result state has brief_id set after dispatch."""
        workflow, mocks = _build_workflow(overall_confidence=0.85)
        state = _make_state()

        result = await workflow.ainvoke(state)

        assert result.brief_id is not None

    @pytest.mark.asyncio
    async def test_full_pipeline_merges_watchlist_and_portfolio(self):
        """End-to-end: scoped_company_ids is populated from both repos."""
        workflow, mocks = _build_workflow(overall_confidence=0.85)
        state = _make_state()

        result = await workflow.ainvoke(state)

        # At least some companies should be scoped
        assert len(result.scoped_company_ids) > 0

    @pytest.mark.asyncio
    async def test_full_pipeline_brief_type_is_watchlist_scan(self):
        """End-to-end: Brief has type='watchlist_scan'."""
        inserted_brief = None

        async def capture(brief):
            nonlocal inserted_brief
            inserted_brief = brief
            row = MagicMock()
            row.brief_id = uuid.uuid4()
            return row

        workflow, mocks = _build_workflow(overall_confidence=0.85)
        mocks["brief_repo"].insert_memo = capture

        state = _make_state()
        await workflow.ainvoke(state)

        assert inserted_brief is not None
        assert inserted_brief.type == "watchlist_scan"


class TestWatchlistScanEndToEndHIL:
    @pytest.mark.asyncio
    async def test_full_pipeline_enqueues_hil_on_medium_confidence(self):
        """End-to-end: medium confidence enqueues HIL item."""
        workflow, mocks = _build_workflow(overall_confidence=0.55)
        state = _make_state()

        result = await workflow.ainvoke(state)

        mocks["hil_repo"].create.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_pipeline_does_not_send_email_on_medium_confidence(self):
        """End-to-end: medium confidence does NOT send email."""
        workflow, mocks = _build_workflow(overall_confidence=0.55)
        state = _make_state()

        result = await workflow.ainvoke(state)

        mocks["email_service"].send_watchlist_scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_pipeline_sets_requires_hil_on_medium_confidence(self):
        """End-to-end: result state has requires_hil=True on medium confidence."""
        workflow, mocks = _build_workflow(overall_confidence=0.55)
        state = _make_state()

        result = await workflow.ainvoke(state)

        assert result.requires_hil is True

    @pytest.mark.asyncio
    async def test_full_pipeline_blocks_on_low_confidence(self):
        """End-to-end: low confidence blocks — no brief, no email, no HIL."""
        workflow, mocks = _build_workflow(overall_confidence=0.20)
        state = _make_state()

        result = await workflow.ainvoke(state)

        mocks["brief_repo"].insert_memo.assert_not_called()
        mocks["email_service"].send_watchlist_scan.assert_not_called()
        mocks["hil_repo"].create.assert_not_called()
