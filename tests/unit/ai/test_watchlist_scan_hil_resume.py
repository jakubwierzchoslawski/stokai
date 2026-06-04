"""
Unit tests for WatchlistScan HIL resume integration.

TDD: written before implementation — PLAN-F-008 TASK-011.

Tests:
  - HIL approval → dispatch (brief insert + email)
  - HIL rejection → block_and_notify (no brief, no email)
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
        "overall_confidence": 0.55,  # Medium confidence — was in HIL
        "requires_hil": True,
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


def _make_workflow() -> tuple[WatchlistScanWorkflow, dict]:
    """Build WatchlistScanWorkflow with all deps mocked for HIL resume tests."""
    from unittest.mock import AsyncMock, MagicMock

    watchlist_repo = AsyncMock()
    watchlist_repo.list_company_ids = AsyncMock(return_value=[])
    portfolio_repo = AsyncMock()
    portfolio_repo.list_company_ids = AsyncMock(return_value=[])
    geo_event_repo = AsyncMock()
    geo_event_repo.list_for_companies = AsyncMock(return_value=[])
    score_repo = AsyncMock()
    score_repo.list_score_changes = AsyncMock(return_value=[])
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

    def _make_agent():
        output = MagicMock()
        output.cost_usd = 0.01
        output.relevant_events = []
        output.anomalies = []
        output.high_anomaly_company_ids = []
        output.recommendations = []
        output.overall_confidence = 0.80
        output.report = {"sections": ["overview"]}
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)
        return agent

    judge_result = MagicMock()
    judge_result.confidence = 0.80
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
        filter_agent=_make_agent(),
        anomaly_agent=_make_agent(),
        analyst_agent=_make_agent(),
        writer_agent=_make_agent(),
        tier1_judge=tier1_judge,
        cost_ceiling_usd=1.00,
    )

    return workflow, {
        "brief_repo": brief_repo,
        "email_service": email_service,
        "hil_repo": hil_repo,
    }


class TestHILResumeApproval:
    @pytest.mark.asyncio
    async def test_approval_inserts_brief(self):
        """HIL approval must insert a Brief row."""
        workflow, mocks = _make_workflow()
        state = _make_state()

        await workflow.resume_from_hil(state, approved=True)

        mocks["brief_repo"].insert_memo.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_sends_email(self):
        """HIL approval must send email via email_service."""
        workflow, mocks = _make_workflow()
        state = _make_state()

        await workflow.resume_from_hil(state, approved=True)

        mocks["email_service"].send_watchlist_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_brief_type_is_watchlist_scan(self):
        """Brief inserted on approval must have type='watchlist_scan'."""
        inserted_brief = None

        async def capture_insert(brief):
            nonlocal inserted_brief
            inserted_brief = brief
            row = MagicMock()
            row.brief_id = uuid.uuid4()
            return row

        workflow, mocks = _make_workflow()
        mocks["brief_repo"].insert_memo = capture_insert

        state = _make_state(report={"headline": "Reviewed and approved"})
        await workflow.resume_from_hil(state, approved=True)

        assert inserted_brief is not None
        assert inserted_brief.type == "watchlist_scan"

    @pytest.mark.asyncio
    async def test_approval_sets_brief_id_on_returned_state(self):
        """resume_from_hil with approval must set brief_id on returned state."""
        expected_id = uuid.uuid4()
        row = MagicMock()
        row.brief_id = expected_id

        workflow, mocks = _make_workflow()
        mocks["brief_repo"].insert_memo = AsyncMock(return_value=row)

        state = _make_state()
        result = await workflow.resume_from_hil(state, approved=True)

        assert result.brief_id == expected_id


class TestHILResumeRejection:
    @pytest.mark.asyncio
    async def test_rejection_does_not_insert_brief(self):
        """HIL rejection must NOT insert a Brief row."""
        workflow, mocks = _make_workflow()
        state = _make_state()

        await workflow.resume_from_hil(state, approved=False)

        mocks["brief_repo"].insert_memo.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejection_does_not_send_email(self):
        """HIL rejection must NOT send email."""
        workflow, mocks = _make_workflow()
        state = _make_state()

        await workflow.resume_from_hil(state, approved=False)

        mocks["email_service"].send_watchlist_scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejection_returns_state(self):
        """resume_from_hil with rejection returns a WatchlistScanState."""
        workflow, _ = _make_workflow()
        state = _make_state()

        result = await workflow.resume_from_hil(state, approved=False)

        assert isinstance(result, WatchlistScanState)

    @pytest.mark.asyncio
    async def test_rejection_sets_hil_reason(self):
        """Rejected state must have hil_reason set."""
        workflow, _ = _make_workflow()
        state = _make_state()

        result = await workflow.resume_from_hil(state, approved=False)

        assert result.hil_reason is not None
