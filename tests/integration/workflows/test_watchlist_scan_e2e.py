"""
End-to-end integration tests for the Watchlist Scan workflow.

TDD: written before implementation — PLAN-F-008 TASK-016.

Uses:
  - Full compiled graph (build_watchlist_scan_graph)
  - Mock all LLM agent invocations
  - Real DeterministicNodes against mock tool_library
  - Verifies routing for all three confidence paths
  - Verifies budget exceeded handling
  - Verifies empty watchlist graceful completion
  - Verifies PostgreSQL checkpointer is configured when provided

These tests do NOT require a real database connection — they use mock repos.
For full DB integration, set INTEGRATION_DB=true and provide DATABASE_URL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.watchlist_scan.cost_guard import WorkflowBudgetExceededError
from src.ai.workflows.watchlist_scan.graph import build_watchlist_scan_graph
from src.ai.workflows.watchlist_scan.state import WatchlistScanState
from src.ai.workflows.state import WorkflowType


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "workflow_type": WorkflowType.WATCHLIST_SCAN,
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


def _make_agent_definition(
    *,
    relevant_events=None,
    anomalies=None,
    high_anomaly_ids=None,
    recommendations=None,
    report=None,
    confidence=0.85,
    cost_usd=0.05,
) -> AsyncMock:
    """Build a mock AgentDefinition with configurable output."""
    definition = AsyncMock()
    definition.ainvoke = AsyncMock(return_value={
        "relevant_events": relevant_events or [],
        "anomalies": anomalies or [],
        "high_anomaly_ids": high_anomaly_ids or [],
        "recommendations": recommendations or [
            {"action_signal": "HOLD", "company_id": str(uuid.uuid4()), "confidence": confidence}
        ],
        "report": report or {"content": "<html><body><p>Report</p></body></html>"},
        "analogies": [],
        "cost_usd": cost_usd,
        "confidence": confidence,
    })
    return definition


def _make_registry(confidence: float = 0.85) -> MagicMock:
    """Build a mock AgentRegistry returning agents with specified confidence."""
    registry = MagicMock()
    registry.resolve = MagicMock(
        side_effect=lambda role_id: _make_agent_definition(confidence=confidence)
    )
    return registry


_SENTINEL = object()  # sentinel for "use default"


def _make_tool_library(
    watchlist_ids=_SENTINEL,
    portfolio_ids=None,
) -> AsyncMock:
    """Build a mock ToolLibrary."""
    tl = AsyncMock()
    if watchlist_ids is _SENTINEL:
        # Default: one company in watchlist
        tl.get_watchlist = AsyncMock(return_value=[uuid.uuid4()])
    else:
        tl.get_watchlist = AsyncMock(return_value=watchlist_ids)
    tl.get_portfolio_state = AsyncMock(return_value=portfolio_ids or [])
    tl.query_recent_events = AsyncMock(return_value=[])
    tl.get_company_score_history = AsyncMock(
        return_value={"prior_score": 0.5, "current_score": 0.6}
    )
    return tl


def _make_brief_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.insert_brief = AsyncMock(return_value=MagicMock(brief_id=uuid.uuid4()))
    repo.update_sent_at = AsyncMock()
    return repo


def _make_alert_service() -> AsyncMock:
    svc = AsyncMock()
    svc.send_email = AsyncMock()
    return svc


def _make_hil_service() -> AsyncMock:
    svc = AsyncMock()
    svc.enqueue = AsyncMock()
    return svc


def _make_memory_service() -> AsyncMock:
    svc = AsyncMock()
    svc.record_workflow_run = AsyncMock()
    svc.record_workflow_completed = AsyncMock()
    return svc


# ── Test helpers ──────────────────────────────────────────────────────────────


async def _run_graph(
    confidence: float = 0.85,
    watchlist_ids=_SENTINEL,
    portfolio_ids=None,
    cost_ceiling_usd: float = 1.00,
    extra_graph_kwargs=None,
) -> tuple[WatchlistScanState, dict]:
    """Run the watchlist scan graph and return (final_state, mocks)."""
    registry = _make_registry(confidence=confidence)
    tool_library = _make_tool_library(
        watchlist_ids=watchlist_ids,
        portfolio_ids=portfolio_ids,
    )
    brief_repo = _make_brief_repo()
    alert_service = _make_alert_service()
    hil_service = _make_hil_service()
    memory_service = _make_memory_service()

    kwargs = {
        "registry": registry,
        "tool_library": tool_library,
        "cost_ceiling_usd": cost_ceiling_usd,
        "brief_repo": brief_repo,
        "alert_service": alert_service,
        "hil_service": hil_service,
        "memory_service": memory_service,
    }
    if extra_graph_kwargs:
        kwargs.update(extra_graph_kwargs)

    graph = build_watchlist_scan_graph(**kwargs)
    state = _make_state()
    final_state = await graph.ainvoke(state)

    mocks = {
        "brief_repo": brief_repo,
        "alert_service": alert_service,
        "hil_service": hil_service,
        "memory_service": memory_service,
        "registry": registry,
    }
    return final_state, mocks


# ── E2E tests ─────────────────────────────────────────────────────────────────


class TestWatchlistScanE2EAutoDispatch:
    @pytest.mark.asyncio
    async def test_e2e_auto_dispatch_path(self):
        """Mock all agents return confidence 0.85; assert brief persisted and email sent."""
        final_state, mocks = await _run_graph(confidence=0.85)

        mocks["brief_repo"].insert_brief.assert_called_once()
        mocks["alert_service"].send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_e2e_auto_dispatch_sets_brief_id(self):
        """Auto-dispatch path: final state has brief_id set."""
        final_state, mocks = await _run_graph(confidence=0.85)

        assert final_state.brief_id is not None

    @pytest.mark.asyncio
    async def test_e2e_auto_dispatch_requires_hil_false(self):
        """Auto-dispatch path: requires_hil is False."""
        final_state, mocks = await _run_graph(confidence=0.85)

        assert final_state.requires_hil is False


class TestWatchlistScanE2EHILPath:
    @pytest.mark.asyncio
    async def test_e2e_hil_path(self):
        """Mock agents return confidence 0.55; assert HIL enqueued."""
        final_state, mocks = await _run_graph(confidence=0.55)

        mocks["hil_service"].enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_e2e_hil_path_requires_hil_true(self):
        """HIL path: requires_hil is True."""
        final_state, mocks = await _run_graph(confidence=0.55)

        assert final_state.requires_hil is True

    @pytest.mark.asyncio
    async def test_e2e_hil_path_no_email_sent(self):
        """HIL path: no email dispatched."""
        final_state, mocks = await _run_graph(confidence=0.55)

        mocks["alert_service"].send_email.assert_not_called()


class TestWatchlistScanE2EBlockPath:
    @pytest.mark.asyncio
    async def test_e2e_block_path(self):
        """Mock agents return confidence 0.25; assert no brief and episodic log blocked."""
        final_state, mocks = await _run_graph(confidence=0.25)

        mocks["brief_repo"].insert_brief.assert_not_called()
        mocks["alert_service"].send_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_e2e_block_path_episodic_log_status_blocked(self):
        """Block path: episodic memory record_workflow_completed with status='blocked'."""
        final_state, mocks = await _run_graph(confidence=0.25)

        mocks["memory_service"].record_workflow_completed.assert_called_once()
        call_kwargs = mocks["memory_service"].record_workflow_completed.call_args.kwargs
        assert call_kwargs.get("status") == "blocked"

    @pytest.mark.asyncio
    async def test_e2e_block_path_no_report_content_sent(self):
        """Block path: no email with report content is ever sent."""
        final_state, mocks = await _run_graph(confidence=0.25)

        mocks["alert_service"].send_email.assert_not_called()


class TestWatchlistScanE2EBudgetExceeded:
    @pytest.mark.asyncio
    async def test_e2e_budget_exceeded_raises_error(self):
        """Cost accumulation exceeds $1.00 mid-graph; WorkflowBudgetExceededError raised."""
        # Each agent costs $0.30; 4 agents x $0.30 = $1.20 > $1.00 ceiling
        registry = MagicMock()
        registry.resolve = MagicMock(
            side_effect=lambda role_id: _make_agent_definition(
                confidence=0.85, cost_usd=0.30
            )
        )
        tool_library = _make_tool_library()
        brief_repo = _make_brief_repo()
        alert_service = _make_alert_service()
        hil_service = _make_hil_service()

        graph = build_watchlist_scan_graph(
            registry=registry,
            tool_library=tool_library,
            cost_ceiling_usd=0.40,  # Very low ceiling to trigger early
            brief_repo=brief_repo,
            alert_service=alert_service,
            hil_service=hil_service,
        )
        state = _make_state()

        with pytest.raises(WorkflowBudgetExceededError):
            await graph.ainvoke(state)


class TestWatchlistScanE2EEmptyWatchlist:
    @pytest.mark.asyncio
    async def test_e2e_empty_watchlist_completes_gracefully(self):
        """User has no watchlist; workflow completes without exception."""
        # Explicitly pass empty list (not sentinel)
        tool_library = _make_tool_library(watchlist_ids=[], portfolio_ids=[])
        registry = _make_registry(confidence=0.85)
        brief_repo = _make_brief_repo()
        alert_service = _make_alert_service()
        hil_service = _make_hil_service()

        graph = build_watchlist_scan_graph(
            registry=registry,
            tool_library=tool_library,
            cost_ceiling_usd=1.00,
            brief_repo=brief_repo,
            alert_service=alert_service,
            hil_service=hil_service,
        )
        state = _make_state()
        final_state = await graph.ainvoke(state)

        # Should complete without exception (empty watchlist is valid)
        assert final_state is not None
        assert final_state.scoped_company_ids == []

    @pytest.mark.asyncio
    async def test_e2e_empty_watchlist_no_crash(self):
        """Empty watchlist workflow path completes — no exception thrown."""
        tool_library = _make_tool_library(watchlist_ids=[], portfolio_ids=[])
        registry = _make_registry(confidence=0.85)
        brief_repo = _make_brief_repo()
        alert_service = _make_alert_service()
        hil_service = _make_hil_service()

        graph = build_watchlist_scan_graph(
            registry=registry,
            tool_library=tool_library,
            cost_ceiling_usd=1.00,
            brief_repo=brief_repo,
            alert_service=alert_service,
            hil_service=hil_service,
        )
        state = _make_state()
        final_state = await graph.ainvoke(state)

        assert final_state is not None


class TestWatchlistScanE2ECheckpointer:
    def test_e2e_postgresql_checkpointer_stored_in_graph(self):
        """build_watchlist_scan_graph stores pg_checkpointer when provided."""
        registry = _make_registry()
        tool_library = _make_tool_library()
        pg_checkpointer = MagicMock()
        pg_checkpointer.name = "AsyncPostgresSaver"

        graph = build_watchlist_scan_graph(
            registry=registry,
            tool_library=tool_library,
            pg_checkpointer=pg_checkpointer,
        )

        assert graph._pg_checkpointer is pg_checkpointer

    def test_graph_accepts_none_checkpointer(self):
        """build_watchlist_scan_graph works without a checkpointer (test env)."""
        registry = _make_registry()
        tool_library = _make_tool_library()

        graph = build_watchlist_scan_graph(
            registry=registry,
            tool_library=tool_library,
            pg_checkpointer=None,
        )

        assert graph._pg_checkpointer is None


class TestWatchlistScanWorkflowState:
    def test_state_workflow_type_is_watchlist_scan(self):
        """WatchlistScanState.workflow_type defaults to WATCHLIST_SCAN."""
        state = _make_state()
        assert state.workflow_type == WorkflowType.WATCHLIST_SCAN

    def test_state_all_collections_default_empty(self):
        """All collection fields default to empty lists/dicts."""
        state = _make_state()
        assert state.watchlist_companies == []
        assert state.portfolio_companies == []
        assert state.scoped_company_ids == []
        assert state.today_events == []
        assert state.relevant_events == []
        assert state.score_changes == []
        assert state.anomalies == []
        assert state.high_anomaly_company_ids == []
        assert state.analogies == {}
        assert state.recommendations == []
        assert state.report is None
        assert state.overall_confidence == 0.0
        assert state.cost_usd == 0.0
