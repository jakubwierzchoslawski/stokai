"""
Unit tests for WatchlistScan AgentNodes.

TDD: written before implementation — PLAN-F-008 TASK-003.

Nodes tested:
  filter_relevant_events  — invokes agent, populates relevant_events
  detect_anomalies        — invokes agent, populates anomalies + high_anomaly_company_ids
  run_watchlist_analyst   — invokes agent, sets overall_confidence
  narrative_writer        — invokes agent, produces report dict

Cost ceiling at $1.00 raises WorkflowCostLimitError.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.watchlist_scan_nodes import (
    WATCHLIST_COST_CEILING_USD,
    detect_anomalies,
    filter_relevant_events,
    narrative_writer,
    run_watchlist_analyst,
)
from src.ai.workflows.watchlist_scan_state import WatchlistScanState


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


def _make_agent_output(**attrs) -> Any:
    """Create a mock agent output with specified attributes."""
    output = MagicMock()
    output.cost_usd = attrs.get("cost_usd", 0.10)
    output.confidence = attrs.get("confidence", 0.75)
    for key, val in attrs.items():
        setattr(output, key, val)
    return output


# ── filter_relevant_events ────────────────────────────────────────────────────


class TestFilterRelevantEvents:
    @pytest.mark.asyncio
    async def test_invokes_agent_and_sets_relevant_events(self):
        """Node invokes agent and populates relevant_events."""
        events = [{"event_id": str(uuid.uuid4()), "title": "Oil price spike"}]
        output = _make_agent_output(relevant_events=events, cost_usd=0.05)

        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(today_events=[{"event_id": str(uuid.uuid4())}])
        result = await filter_relevant_events(state, agent=agent)

        agent.invoke.assert_called_once_with(state)
        assert result.relevant_events == events

    @pytest.mark.asyncio
    async def test_accumulates_cost(self):
        """Cost from agent output is added to state.cost_usd."""
        output = _make_agent_output(relevant_events=[], cost_usd=0.15)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(cost_usd=0.20)
        result = await filter_relevant_events(state, agent=agent)

        assert abs(result.cost_usd - 0.35) < 1e-9

    @pytest.mark.asyncio
    async def test_cost_ceiling_raises_before_agent_call(self):
        """Cost ceiling at $1.00 raises WorkflowCostLimitError before agent."""
        guard = CostCeilingGuard(WATCHLIST_COST_CEILING_USD)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=_make_agent_output())

        state = _make_state(cost_usd=1.00)  # at ceiling
        with pytest.raises(WorkflowCostLimitError):
            await filter_relevant_events(state, agent=agent, cost_guard=guard)

        agent.invoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_cost_guard_does_not_raise(self):
        """Node works without cost_guard (guard is optional)."""
        output = _make_agent_output(relevant_events=[])
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(cost_usd=5.00)  # very high but no guard
        result = await filter_relevant_events(state, agent=agent, cost_guard=None)

        assert result is not None


# ── detect_anomalies ──────────────────────────────────────────────────────────


class TestDetectAnomalies:
    @pytest.mark.asyncio
    async def test_populates_anomalies_and_high_anomaly_ids(self):
        """Node populates anomalies and high_anomaly_company_ids from agent output."""
        company_id = uuid.uuid4()
        anomalies_data = [{"company_id": str(company_id), "severity": "high"}]
        high_ids = [company_id]
        output = _make_agent_output(
            anomalies=anomalies_data,
            high_anomaly_company_ids=high_ids,
            cost_usd=0.08,
        )

        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state()
        result = await detect_anomalies(state, agent=agent)

        assert result.anomalies == anomalies_data
        assert result.high_anomaly_company_ids == high_ids

    @pytest.mark.asyncio
    async def test_accumulates_cost(self):
        """Cost from agent is accumulated."""
        output = _make_agent_output(anomalies=[], high_anomaly_company_ids=[], cost_usd=0.12)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(cost_usd=0.30)
        result = await detect_anomalies(state, agent=agent)

        assert abs(result.cost_usd - 0.42) < 1e-9

    @pytest.mark.asyncio
    async def test_cost_ceiling_raises_at_1_00(self):
        """CostCeilingGuard at $1.00 raises WorkflowCostLimitError."""
        guard = CostCeilingGuard(WATCHLIST_COST_CEILING_USD)
        agent = MagicMock()

        state = _make_state(cost_usd=1.00)
        with pytest.raises(WorkflowCostLimitError):
            await detect_anomalies(state, agent=agent, cost_guard=guard)

        agent.invoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_invokes_correct_agent(self):
        """Agent is invoked with the current state."""
        output = _make_agent_output(anomalies=[], high_anomaly_company_ids=[])
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state()
        await detect_anomalies(state, agent=agent)

        agent.invoke.assert_called_once_with(state)


# ── run_watchlist_analyst ─────────────────────────────────────────────────────


class TestRunWatchlistAnalyst:
    @pytest.mark.asyncio
    async def test_sets_overall_confidence(self):
        """overall_confidence must be set from agent output."""
        output = _make_agent_output(
            recommendations=[{"action": "BUY", "company": "AAPL"}],
            overall_confidence=0.82,
            cost_usd=0.20,
        )
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state()
        result = await run_watchlist_analyst(state, agent=agent)

        assert abs(result.overall_confidence - 0.82) < 1e-9

    @pytest.mark.asyncio
    async def test_sets_recommendations(self):
        """recommendations must be set from agent output."""
        recs = [{"action": "SELL", "company": "TSLA"}]
        output = _make_agent_output(recommendations=recs, overall_confidence=0.75)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state()
        result = await run_watchlist_analyst(state, agent=agent)

        assert result.recommendations == recs

    @pytest.mark.asyncio
    async def test_cost_ceiling_raises_at_1_00(self):
        """CostCeilingGuard raises at $1.00."""
        guard = CostCeilingGuard(WATCHLIST_COST_CEILING_USD)
        agent = MagicMock()

        state = _make_state(cost_usd=1.01)
        with pytest.raises(WorkflowCostLimitError):
            await run_watchlist_analyst(state, agent=agent, cost_guard=guard)

    @pytest.mark.asyncio
    async def test_stores_confidence_in_confidence_scores(self):
        """confidence_scores dict should be updated with watchlist_analyst key."""
        output = _make_agent_output(
            recommendations=[], overall_confidence=0.78, cost_usd=0.05
        )
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state()
        result = await run_watchlist_analyst(state, agent=agent)

        assert "watchlist_analyst" in result.confidence_scores
        assert abs(result.confidence_scores["watchlist_analyst"] - 0.78) < 1e-9


# ── narrative_writer ──────────────────────────────────────────────────────────


class TestNarrativeWriter:
    @pytest.mark.asyncio
    async def test_sets_report(self):
        """report dict must be populated from agent output."""
        report_data = {"headline": "Afternoon scan complete", "sections": ["overview"]}
        output = _make_agent_output(report=report_data, cost_usd=0.05)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state()
        result = await narrative_writer(state, agent=agent)

        assert result.report == report_data

    @pytest.mark.asyncio
    async def test_produces_fallback_report_when_agent_returns_none_report(self):
        """If agent output.report is None, a fallback dict is built from state."""
        output = _make_agent_output(report=None, cost_usd=0.05)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(
            recommendations=[{"action": "BUY"}],
            overall_confidence=0.75,
        )
        result = await narrative_writer(state, agent=agent)

        assert result.report is not None
        assert "recommendations" in result.report

    @pytest.mark.asyncio
    async def test_cost_ceiling_raises_at_1_00(self):
        """CostCeilingGuard raises at $1.00."""
        guard = CostCeilingGuard(WATCHLIST_COST_CEILING_USD)
        agent = MagicMock()

        state = _make_state(cost_usd=1.00)
        with pytest.raises(WorkflowCostLimitError):
            await narrative_writer(state, agent=agent, cost_guard=guard)

    @pytest.mark.asyncio
    async def test_accumulates_cost(self):
        """Cost is accumulated from agent output."""
        output = _make_agent_output(report={"text": "done"}, cost_usd=0.09)
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(cost_usd=0.50)
        result = await narrative_writer(state, agent=agent)

        assert abs(result.cost_usd - 0.59) < 1e-9
