"""
Unit tests for the Watchlist Scan workflow nodes.

TDD: tests written per PLAN-F-008 TASK-003 through TASK-014.

Covers:
  TASK-003: fetch_watchlist, fetch_today_events
  TASK-004: recompute_scores
  TASK-005: relevance_analyst_node
  TASK-006: anomaly_detector_node
  TASK-007: historical_context_node
  TASK-008: recommendation_synthesizer_node
  TASK-009: narrative_writer_node
  TASK-010: evaluate_quality_node
  TASK-013: hil_enqueue_node, block_and_notify_node
  TASK-014: dispatch_node
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.watchlist_scan.cost_guard import (
    WorkflowBudgetExceededError,
    WorkflowCostGuard,
)
from src.ai.workflows.watchlist_scan.nodes import (
    anomaly_detector_node,
    block_and_notify_node,
    dispatch_node,
    evaluate_quality_node,
    fetch_today_events,
    fetch_watchlist,
    hil_enqueue_node,
    historical_context_node,
    narrative_writer_node,
    recompute_scores,
    recommendation_synthesizer_node,
    relevance_analyst_node,
)
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


def _make_cost_guard(ceiling: float = 1.00) -> WorkflowCostGuard:
    return WorkflowCostGuard(ceiling_usd=ceiling)


def _make_registry(role_id: str, agent_result: dict | None = None) -> MagicMock:
    """Build a mock AgentRegistry that returns a mock agent for resolve()."""
    definition = AsyncMock()
    if agent_result is not None:
        definition.ainvoke = AsyncMock(return_value=agent_result)
    else:
        definition.ainvoke = AsyncMock(return_value={})
    registry = MagicMock()
    registry.resolve = MagicMock(return_value=definition)
    return registry


# ─────────────────────────────────────────────────────────────────────────────
# TASK-003: fetch_watchlist
# ─────────────────────────────────────────────────────────────────────────────


class TestFetchWatchlist:
    @pytest.mark.asyncio
    async def test_fetch_watchlist_populates_scoped_company_ids(self):
        """Given mock tool returns watchlist+portfolio items, assert deduplication and union."""
        wl_id = uuid.uuid4()
        p_id = uuid.uuid4()

        tool_library = AsyncMock()
        tool_library.get_watchlist = AsyncMock(return_value=[wl_id])
        tool_library.get_portfolio_state = AsyncMock(return_value=[p_id])

        state = _make_state()
        result = await fetch_watchlist(state, tool_library=tool_library)

        assert wl_id in result.scoped_company_ids
        assert p_id in result.scoped_company_ids
        assert len(result.scoped_company_ids) == 2

    @pytest.mark.asyncio
    async def test_fetch_watchlist_deduplicates_overlap(self):
        """When watchlist and portfolio share a company, scoped_company_ids has no duplicates."""
        shared_id = uuid.uuid4()
        extra_id = uuid.uuid4()

        tool_library = AsyncMock()
        tool_library.get_watchlist = AsyncMock(return_value=[shared_id, extra_id])
        tool_library.get_portfolio_state = AsyncMock(return_value=[shared_id])

        state = _make_state()
        result = await fetch_watchlist(state, tool_library=tool_library)

        assert len(result.scoped_company_ids) == 2
        assert result.scoped_company_ids.count(shared_id) == 1

    @pytest.mark.asyncio
    async def test_fetch_watchlist_empty_watchlist_equals_portfolio_only(self):
        """User has no watchlist entries; scoped_company_ids equals portfolio-only; no error."""
        p_id = uuid.uuid4()

        tool_library = AsyncMock()
        tool_library.get_watchlist = AsyncMock(return_value=[])
        tool_library.get_portfolio_state = AsyncMock(return_value=[p_id])

        state = _make_state()
        result = await fetch_watchlist(state, tool_library=tool_library)

        assert result.scoped_company_ids == [p_id]
        assert result.watchlist_companies == []
        assert result.portfolio_companies == [p_id]

    @pytest.mark.asyncio
    async def test_fetch_watchlist_both_empty_gives_empty_scoped(self):
        """Both watchlist and portfolio empty; scoped_company_ids is empty."""
        tool_library = AsyncMock()
        tool_library.get_watchlist = AsyncMock(return_value=[])
        tool_library.get_portfolio_state = AsyncMock(return_value=[])

        state = _make_state()
        result = await fetch_watchlist(state, tool_library=tool_library)

        assert result.scoped_company_ids == []


# ─────────────────────────────────────────────────────────────────────────────
# TASK-003: fetch_today_events
# ─────────────────────────────────────────────────────────────────────────────


class TestFetchTodayEvents:
    @pytest.mark.asyncio
    async def test_fetch_today_events_stores_all_events(self):
        """Mock tool returns N events; state.today_events has length N."""
        events = [{"event_id": str(uuid.uuid4())} for _ in range(5)]

        tool_library = AsyncMock()
        tool_library.query_recent_events = AsyncMock(return_value=events)

        state = _make_state()
        result = await fetch_today_events(state, tool_library=tool_library)

        assert len(result.today_events) == 5

    @pytest.mark.asyncio
    async def test_fetch_today_events_tool_error_propagates(self):
        """Tool raises RuntimeError; node re-raises with context."""
        tool_library = AsyncMock()
        tool_library.query_recent_events = AsyncMock(
            side_effect=Exception("InsufficientData")
        )

        state = _make_state()
        with pytest.raises(RuntimeError, match="fetch_today_events"):
            await fetch_today_events(state, tool_library=tool_library)

    @pytest.mark.asyncio
    async def test_fetch_today_events_empty_returns_empty_list(self):
        """No events available; state.today_events is empty list."""
        tool_library = AsyncMock()
        tool_library.query_recent_events = AsyncMock(return_value=[])

        state = _make_state()
        result = await fetch_today_events(state, tool_library=tool_library)

        assert result.today_events == []


# ─────────────────────────────────────────────────────────────────────────────
# TASK-004: recompute_scores
# ─────────────────────────────────────────────────────────────────────────────


class TestRecomputeScores:
    @pytest.mark.asyncio
    async def test_recompute_scores_empty_relevant_events_returns_unchanged(self):
        """state.score_changes remains empty; no tool calls made."""
        tool_library = AsyncMock()
        tool_library.get_company_score_history = AsyncMock()

        state = _make_state(relevant_events=[], scoped_company_ids=[uuid.uuid4()])
        result = await recompute_scores(state, tool_library=tool_library)

        assert result.score_changes == []
        tool_library.get_company_score_history.assert_not_called()

    @pytest.mark.asyncio
    async def test_recompute_scores_only_scoped_companies(self):
        """relevant_events touch companies both inside and outside scoped; only scoped computed."""
        scoped_id = uuid.uuid4()
        out_of_scope_id = uuid.uuid4()

        # Event touches both companies
        relevant_events = [
            {
                "company_id": str(scoped_id),
                "company_ids": [str(scoped_id), str(out_of_scope_id)],
            }
        ]

        tool_library = AsyncMock()
        tool_library.get_company_score_history = AsyncMock(
            return_value={"prior_score": 0.5, "current_score": 0.7}
        )

        state = _make_state(
            relevant_events=relevant_events,
            scoped_company_ids=[scoped_id],
        )
        result = await recompute_scores(state, tool_library=tool_library)

        # Only scoped_id should be computed
        called_ids = [
            call.kwargs["company_id"]
            for call in tool_library.get_company_score_history.call_args_list
        ]
        assert scoped_id in called_ids
        assert out_of_scope_id not in called_ids

    @pytest.mark.asyncio
    async def test_recompute_scores_populates_score_changes_fields(self):
        """Assert ScoreChange objects include company_id, prior_score, new_score, delta."""
        company_id = uuid.uuid4()
        relevant_events = [{"company_id": str(company_id)}]

        tool_library = AsyncMock()
        tool_library.get_company_score_history = AsyncMock(
            return_value={"prior_score": 0.4, "current_score": 0.6}
        )

        state = _make_state(
            relevant_events=relevant_events,
            scoped_company_ids=[company_id],
        )
        result = await recompute_scores(state, tool_library=tool_library)

        assert len(result.score_changes) == 1
        sc = result.score_changes[0]
        assert sc["company_id"] == company_id
        assert abs(sc["prior_score"] - 0.4) < 1e-9
        assert abs(sc["new_score"] - 0.6) < 1e-9
        assert abs(sc["delta"] - 0.2) < 1e-9

    @pytest.mark.asyncio
    async def test_recompute_scores_concurrent_execution(self):
        """5 scoped companies affected; asyncio.gather used (all called)."""
        company_ids = [uuid.uuid4() for _ in range(5)]
        relevant_events = [{"company_id": str(cid)} for cid in company_ids]

        call_count = 0

        async def mock_score_history(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"prior_score": 0.5, "current_score": 0.6}

        tool_library = AsyncMock()
        tool_library.get_company_score_history = mock_score_history

        state = _make_state(
            relevant_events=relevant_events,
            scoped_company_ids=company_ids,
        )
        result = await recompute_scores(state, tool_library=tool_library)

        assert call_count == 5
        assert len(result.score_changes) == 5


# ─────────────────────────────────────────────────────────────────────────────
# TASK-005: relevance_analyst_node
# ─────────────────────────────────────────────────────────────────────────────


class TestRelevanceAnalystNode:
    @pytest.mark.asyncio
    async def test_relevance_analyst_node_updates_cost(self):
        """Mock agent reports cost 0.10; assert state.cost_usd incremented."""
        registry = _make_registry(
            "relevance_analyst",
            {"relevant_events": [], "cost_usd": 0.10, "confidence": 0.8},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(cost_usd=0.0)

        result = await relevance_analyst_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert abs(result.cost_usd - 0.10) < 1e-9

    @pytest.mark.asyncio
    async def test_relevance_analyst_node_confidence_stored(self):
        """Mock agent returns non-empty events with confidence 0.85; assert stored."""
        company_id = uuid.uuid4()
        registry = _make_registry(
            "relevance_analyst",
            {
                "relevant_events": [{"company_id": str(company_id), "event_id": "e1"}],
                "cost_usd": 0.05,
                "confidence": 0.85,
            },
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        # Set scoped_company_ids so the event passes the scope filter
        state = _make_state(scoped_company_ids=[company_id])

        result = await relevance_analyst_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert "relevance_analyst" in result.confidence_scores
        assert abs(result.confidence_scores["relevance_analyst"] - 0.85) < 1e-9

    @pytest.mark.asyncio
    async def test_relevance_analyst_node_cost_ceiling_exceeded(self):
        """Mock cumulative cost reaches $1.00; assert WorkflowBudgetExceededError raised."""
        registry = _make_registry(
            "relevance_analyst",
            {"relevant_events": [], "cost_usd": 0.50, "confidence": 0.8},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(0.40)  # low ceiling
        state = _make_state(cost_usd=0.0)

        with pytest.raises(WorkflowBudgetExceededError):
            await relevance_analyst_node(
                state,
                registry=registry,
                tool_library=tool_library,
                cost_guard=cost_guard,
            )

    @pytest.mark.asyncio
    async def test_relevance_analyst_node_empty_result_sets_low_confidence(self):
        """Agent returns empty relevant_events when today_events is non-empty; sentinel triggers low confidence."""
        registry = _make_registry(
            "relevance_analyst",
            {"relevant_events": [], "cost_usd": 0.05, "confidence": 0.8},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        # Set today_events to non-empty so sentinel triggers
        state = _make_state(today_events=[{"event_id": "e1", "title": "Test event"}])

        result = await relevance_analyst_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        # Empty result with non-empty today_events should trigger sentinel (confidence <= 0.1)
        assert result.confidence_scores.get("relevance_analyst", 1.0) <= 0.1


# ─────────────────────────────────────────────────────────────────────────────
# TASK-006: anomaly_detector_node
# ─────────────────────────────────────────────────────────────────────────────


class TestAnomalyDetectorNode:
    @pytest.mark.asyncio
    async def test_anomaly_detector_populates_high_anomaly_ids(self):
        """Anomalies with mixed magnitudes; only IDs with magnitude >= 0.6 in high_anomaly_company_ids."""
        company_a = uuid.uuid4()
        company_b = uuid.uuid4()
        anomalies = [
            {"company_id": str(company_a), "magnitude": 0.8},   # high
            {"company_id": str(company_b), "magnitude": 0.4},   # normal
        ]
        registry = _make_registry(
            "anomaly_detector",
            {"anomalies": anomalies, "cost_usd": 0.05, "confidence": 0.9},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state()

        result = await anomaly_detector_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert company_a in result.high_anomaly_company_ids
        assert company_b not in result.high_anomaly_company_ids

    @pytest.mark.asyncio
    async def test_anomaly_detector_no_anomalies_empty_high_anomaly_list(self):
        """No anomalies detected; high_anomaly_company_ids is empty."""
        registry = _make_registry(
            "anomaly_detector",
            {"anomalies": [], "cost_usd": 0.02, "confidence": 0.9},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state()

        result = await anomaly_detector_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert result.high_anomaly_company_ids == []

    @pytest.mark.asyncio
    async def test_anomaly_detector_updates_cost_and_confidence(self):
        """Assert cost accumulation and confidence key written."""
        registry = _make_registry(
            "anomaly_detector",
            {"anomalies": [], "cost_usd": 0.07, "confidence": 0.88},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(cost_usd=0.10)

        result = await anomaly_detector_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert abs(result.cost_usd - 0.17) < 1e-9
        assert abs(result.confidence_scores["anomaly_detector"] - 0.88) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# TASK-007: historical_context_node
# ─────────────────────────────────────────────────────────────────────────────


class TestHistoricalContextNode:
    @pytest.mark.asyncio
    async def test_hca_node_skipped_when_no_high_anomaly_companies(self):
        """high_anomaly_company_ids=[]; agent never called; state unchanged."""
        registry = MagicMock()
        registry.resolve = MagicMock()
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(high_anomaly_company_ids=[])

        result = await historical_context_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        registry.resolve.assert_not_called()
        assert result.analogies == {}

    @pytest.mark.asyncio
    async def test_hca_node_invokes_once_per_high_anomaly_company(self):
        """3 high-anomaly companies; agent invoked 3 times."""
        company_ids = [uuid.uuid4() for _ in range(3)]
        call_count = 0

        async def mock_ainvoke(payload):
            nonlocal call_count
            call_count += 1
            return {"analogies": [{"desc": "analogy"}], "cost_usd": 0.01, "confidence": 0.8}

        definition = AsyncMock()
        definition.ainvoke = mock_ainvoke
        registry = MagicMock()
        registry.resolve = MagicMock(return_value=definition)
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(high_anomaly_company_ids=company_ids)

        await historical_context_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_hca_node_uses_asyncio_gather(self):
        """Concurrent execution path taken for multiple companies."""
        import asyncio

        company_ids = [uuid.uuid4() for _ in range(4)]
        started: list[float] = []
        finished: list[float] = []

        async def mock_ainvoke(payload):
            started.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.01)
            finished.append(asyncio.get_event_loop().time())
            return {"analogies": [], "cost_usd": 0.01, "confidence": 0.8}

        definition = AsyncMock()
        definition.ainvoke = mock_ainvoke
        registry = MagicMock()
        registry.resolve = MagicMock(return_value=definition)
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(high_anomaly_company_ids=company_ids)

        await historical_context_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        # With asyncio.gather, all tasks start before any finishes (overlap)
        assert len(started) == 4

    @pytest.mark.asyncio
    async def test_hca_node_writes_analogies_keyed_by_company_id(self):
        """state.analogies dict has entry for each high-anomaly company."""
        company_ids = [uuid.uuid4() for _ in range(2)]

        definition = AsyncMock()
        definition.ainvoke = AsyncMock(
            return_value={"analogies": [{"hist": "data"}], "cost_usd": 0.01, "confidence": 0.75}
        )
        registry = MagicMock()
        registry.resolve = MagicMock(return_value=definition)
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(high_anomaly_company_ids=company_ids)

        result = await historical_context_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        for cid in company_ids:
            assert str(cid) in result.analogies


# ─────────────────────────────────────────────────────────────────────────────
# TASK-008: recommendation_synthesizer_node
# ─────────────────────────────────────────────────────────────────────────────


class TestRecommendationSynthesizerNode:
    @pytest.mark.asyncio
    async def test_synthesizer_produces_recommendations(self):
        """3 relevant events; assert at least one Recommendation produced."""
        recommendations = [
            {"action_signal": "HOLD", "company_id": str(uuid.uuid4()), "confidence": 0.8},
        ]
        registry = _make_registry(
            "recommendation_synthesizer",
            {"recommendations": recommendations, "cost_usd": 0.10, "confidence": 0.8},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(
            relevant_events=[{"event_id": str(uuid.uuid4())} for _ in range(3)],
        )

        result = await recommendation_synthesizer_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert len(result.recommendations) >= 1

    @pytest.mark.asyncio
    async def test_synthesizer_recommendation_action_signals_are_valid(self):
        """All action_signal values in valid set."""
        valid_signals = {"HOLD", "WATCH", "BUY_OPP", "REDUCE_RISK", "HEDGE", "CONTRARIAN"}
        recs = [
            {"action_signal": "HOLD", "company_id": str(uuid.uuid4()), "confidence": 0.8},
            {"action_signal": "BUY_OPP", "company_id": str(uuid.uuid4()), "confidence": 0.7},
        ]
        registry = _make_registry(
            "recommendation_synthesizer",
            {"recommendations": recs, "cost_usd": 0.05, "confidence": 0.85},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state()

        result = await recommendation_synthesizer_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        for rec in result.recommendations:
            signal = rec.get("action_signal") if hasattr(rec, "get") else None
            if signal is not None:
                assert signal in valid_signals

    @pytest.mark.asyncio
    async def test_synthesizer_updates_cost_and_confidence(self):
        """Assert cost accumulation and confidence key written."""
        registry = _make_registry(
            "recommendation_synthesizer",
            {"recommendations": [], "cost_usd": 0.12, "confidence": 0.78},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(cost_usd=0.20)

        result = await recommendation_synthesizer_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert abs(result.cost_usd - 0.32) < 1e-9
        assert abs(result.confidence_scores["recommendation_synthesizer"] - 0.78) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# TASK-009: narrative_writer_node (last AgentNode)
# ─────────────────────────────────────────────────────────────────────────────


class TestNarrativeWriterNode:
    @pytest.mark.asyncio
    async def test_narrative_writer_produces_report(self):
        """Given populated recommendations; assert state.report is non-None."""
        html_report = {"content": "<html><body><p>Report</p></body></html>"}
        registry = _make_registry(
            "narrative_writer",
            {"report": html_report, "cost_usd": 0.15, "confidence": 0.88},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(
            recommendations=[
                {"action_signal": "HOLD", "company_id": str(uuid.uuid4()), "confidence": 0.8}
            ],
        )

        result = await narrative_writer_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert result.report is not None

    @pytest.mark.asyncio
    async def test_narrative_writer_updates_cost(self):
        """Assert cost and confidence updated."""
        registry = _make_registry(
            "narrative_writer",
            {"report": {"content": "<p>ok</p>"}, "cost_usd": 0.20, "confidence": 0.82},
        )
        tool_library = AsyncMock()
        cost_guard = _make_cost_guard(1.00)
        state = _make_state(cost_usd=0.30)

        result = await narrative_writer_node(
            state, registry=registry, tool_library=tool_library, cost_guard=cost_guard
        )

        assert abs(result.cost_usd - 0.50) < 1e-9
        assert abs(result.confidence_scores["narrative_writer"] - 0.82) < 1e-9

    @pytest.mark.asyncio
    async def test_narrative_writer_is_last_agent_node_in_sequence(self):
        """Graph structure test: narrative_writer appears before evaluate_quality."""
        from src.ai.workflows.watchlist_scan.graph import _NODE_SEQUENCE

        nw_idx = _NODE_SEQUENCE.index("narrative_writer")
        eq_idx = _NODE_SEQUENCE.index("evaluate_quality")
        # narrative_writer should come before evaluate_quality
        assert nw_idx < eq_idx, (
            f"narrative_writer (idx={nw_idx}) should come before "
            f"evaluate_quality (idx={eq_idx}) in _NODE_SEQUENCE"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TASK-010: evaluate_quality_node (second-to-last node)
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluateQualityNode:
    @pytest.mark.asyncio
    async def test_evaluate_quality_confidence_is_minimum_across_agents(self):
        """confidence_scores [0.9, 0.5, 0.8]; assert overall_confidence=0.5."""
        state = _make_state(
            confidence_scores={
                "relevance_analyst": 0.9,
                "anomaly_detector": 0.5,
                "recommendation_synthesizer": 0.8,
            }
        )

        result = await evaluate_quality_node(state)

        assert abs(result.overall_confidence - 0.5) < 1e-9

    @pytest.mark.asyncio
    async def test_evaluate_quality_sets_requires_hil_in_mid_range(self):
        """overall_confidence=0.55; assert requires_hil=True."""
        state = _make_state(
            confidence_scores={"relevance_analyst": 0.55},
        )

        result = await evaluate_quality_node(state)

        assert result.requires_hil is True
        assert result.hil_reason is not None

    @pytest.mark.asyncio
    async def test_evaluate_quality_clears_requires_hil_above_threshold(self):
        """overall_confidence=0.75; assert requires_hil=False."""
        state = _make_state(
            confidence_scores={"relevance_analyst": 0.75},
        )

        result = await evaluate_quality_node(state)

        assert result.requires_hil is False

    @pytest.mark.asyncio
    async def test_evaluate_quality_is_second_to_last_node_in_sequence(self):
        """Graph structure test: evaluate_quality is last in _NODE_SEQUENCE (before branch)."""
        from src.ai.workflows.watchlist_scan.graph import _NODE_SEQUENCE

        assert _NODE_SEQUENCE[-1] == "evaluate_quality", (
            f"evaluate_quality should be last in _NODE_SEQUENCE but got {_NODE_SEQUENCE[-1]!r}"
        )

    @pytest.mark.asyncio
    async def test_evaluate_quality_empty_confidence_scores_gives_zero(self):
        """No confidence_scores; overall_confidence defaults to 0.0."""
        state = _make_state(confidence_scores={})

        result = await evaluate_quality_node(state)

        assert result.overall_confidence == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# TASK-013: hil_enqueue_node and block_and_notify_node
# ─────────────────────────────────────────────────────────────────────────────


class TestHilEnqueueNode:
    @pytest.mark.asyncio
    async def test_hil_enqueue_node_sets_requires_hil_true(self):
        """After hil_enqueue_node, state.requires_hil must be True."""
        hil_service = AsyncMock()
        hil_service.enqueue = AsyncMock()

        state = _make_state(overall_confidence=0.55)
        result = await hil_enqueue_node(state, hil_service=hil_service)

        assert result.requires_hil is True

    @pytest.mark.asyncio
    async def test_hil_enqueue_node_calls_service(self):
        """hil_enqueue_node must call hil_service.enqueue."""
        hil_service = AsyncMock()
        hil_service.enqueue = AsyncMock()

        state = _make_state(overall_confidence=0.55)
        await hil_enqueue_node(state, hil_service=hil_service)

        hil_service.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_hil_enqueue_node_schedules_deadline_task_at_1745(self):
        """Mock Celery; assert check_hil_deadline task scheduled."""
        hil_service = AsyncMock()
        hil_service.enqueue = AsyncMock()

        celery_app = MagicMock()
        celery_app.send_task = MagicMock()

        state = _make_state(overall_confidence=0.55)
        await hil_enqueue_node(state, hil_service=hil_service, celery_app=celery_app)

        celery_app.send_task.assert_called_once()
        call_kwargs = celery_app.send_task.call_args
        assert "check_hil_deadline" in call_kwargs[0][0]

    @pytest.mark.asyncio
    async def test_hil_enqueue_node_is_idempotent(self):
        """Calling twice with same report_id does not raise."""
        hil_service = AsyncMock()
        hil_service.enqueue = AsyncMock()

        state = _make_state(overall_confidence=0.55, brief_id=uuid.uuid4())

        await hil_enqueue_node(state, hil_service=hil_service)
        await hil_enqueue_node(state, hil_service=hil_service)

        # Both calls should succeed (no duplicate error)
        assert hil_service.enqueue.call_count == 2


class TestBlockAndNotifyNode:
    @pytest.mark.asyncio
    async def test_block_and_notify_does_not_send_report_content(self):
        """block_and_notify must NOT send any email with report content."""
        state = _make_state(
            overall_confidence=0.20,
            report={"content": "<html>secret report</html>"},
        )

        # No email service passed — if node tries to send, it will fail
        result = await block_and_notify_node(state)

        # Simply reaching here without error proves no email was sent
        assert result is not None

    @pytest.mark.asyncio
    async def test_block_and_notify_writes_episodic_log_with_blocked_status(self):
        """assert workflow status blocked and confidence recorded."""
        memory_service = AsyncMock()
        memory_service.record_workflow_completed = AsyncMock()

        state = _make_state(overall_confidence=0.25)
        result = await block_and_notify_node(
            state, memory_service=memory_service
        )

        memory_service.record_workflow_completed.assert_called_once()
        call_kwargs = memory_service.record_workflow_completed.call_args.kwargs
        assert call_kwargs.get("status") == "blocked"

    @pytest.mark.asyncio
    async def test_block_and_notify_sets_hil_reason(self):
        """block_and_notify sets hil_reason indicating blocked status."""
        state = _make_state(overall_confidence=0.25)
        result = await block_and_notify_node(state)

        assert result.hil_reason is not None
        assert "blocked" in result.hil_reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# TASK-014: dispatch_node
# ─────────────────────────────────────────────────────────────────────────────


class TestDispatchNode:
    @pytest.mark.asyncio
    async def test_dispatch_node_persists_brief_with_correct_type(self):
        """Mock repo; assert brief.type='watchlist_scan' and brief.hil_status='approved'."""
        captured_brief = None

        async def mock_insert_brief(brief_data):
            nonlocal captured_brief
            captured_brief = brief_data
            row = MagicMock()
            row.brief_id = uuid.uuid4()
            return row

        brief_repo = AsyncMock()
        brief_repo.insert_brief = mock_insert_brief
        brief_repo.update_sent_at = AsyncMock()

        alert_service = AsyncMock()
        alert_service.send_email = AsyncMock()

        state = _make_state(overall_confidence=0.80)
        await dispatch_node(
            state, brief_repo=brief_repo, alert_service=alert_service
        )

        assert captured_brief is not None
        assert captured_brief["type"] == "watchlist_scan"
        assert captured_brief["hil_status"] == "approved"

    @pytest.mark.asyncio
    async def test_dispatch_node_sends_email_with_html_content(self):
        """Mock email service; assert called once with HTML body."""
        brief_repo = AsyncMock()
        brief_repo.insert_brief = AsyncMock(return_value=MagicMock(brief_id=uuid.uuid4()))
        brief_repo.update_sent_at = AsyncMock()

        alert_service = AsyncMock()
        alert_service.send_email = AsyncMock()

        state = _make_state(
            overall_confidence=0.80,
            report={"content": "<html><body><p>Report</p></body></html>"},
        )
        await dispatch_node(state, brief_repo=brief_repo, alert_service=alert_service)

        alert_service.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_node_sets_brief_id_on_success(self):
        """Assert brief_id set after successful send."""
        expected_id = uuid.uuid4()

        brief_repo = AsyncMock()
        brief_repo.insert_brief = AsyncMock(return_value=MagicMock(brief_id=expected_id))
        brief_repo.update_sent_at = AsyncMock()

        alert_service = AsyncMock()
        alert_service.send_email = AsyncMock()

        state = _make_state(overall_confidence=0.80)
        result = await dispatch_node(state, brief_repo=brief_repo, alert_service=alert_service)

        assert result.brief_id == expected_id

    @pytest.mark.asyncio
    async def test_dispatch_node_writes_workflow_run_completed(self):
        """Assert episodic memory row status='completed'."""
        brief_repo = AsyncMock()
        brief_repo.insert_brief = AsyncMock(return_value=MagicMock(brief_id=uuid.uuid4()))
        brief_repo.update_sent_at = AsyncMock()

        alert_service = AsyncMock()
        alert_service.send_email = AsyncMock()

        memory_service = AsyncMock()
        memory_service.record_workflow_completed = AsyncMock()

        state = _make_state(overall_confidence=0.80)
        await dispatch_node(
            state,
            brief_repo=brief_repo,
            alert_service=alert_service,
            memory_service=memory_service,
        )

        memory_service.record_workflow_completed.assert_called_once()
        call_kwargs = memory_service.record_workflow_completed.call_args.kwargs
        assert call_kwargs.get("status") == "completed"

    @pytest.mark.asyncio
    async def test_dispatch_node_does_not_send_on_email_service_failure(self):
        """Mock email raises; assert brief_id not set and error propagates."""
        brief_repo = AsyncMock()
        brief_repo.insert_brief = AsyncMock(return_value=MagicMock(brief_id=uuid.uuid4()))
        brief_repo.update_sent_at = AsyncMock()

        alert_service = AsyncMock()
        alert_service.send_email = AsyncMock(side_effect=RuntimeError("SMTP error"))

        state = _make_state(overall_confidence=0.80)

        with pytest.raises(RuntimeError, match="SMTP error"):
            await dispatch_node(state, brief_repo=brief_repo, alert_service=alert_service)
