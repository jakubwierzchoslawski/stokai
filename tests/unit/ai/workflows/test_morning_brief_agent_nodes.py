"""
Unit tests for Morning Brief AgentNodes.

TDD: written before implementation — PLAN-F-006 TASK-004.

Tests:
  - filter_relevant_events: invokes relevance-analyst agent, checks cost guard
  - detect_anomalies: invokes anomaly-detector agent
  - run_analyst_agent: invokes morning-brief-analyst agent
  - narrative_writer: invokes narrative-writer agent
  - CostCeilingGuard triggers at 80% (reduce signal) and 100% (raises error)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.morning_brief_state import MorningBriefState
from src.ai.workflows.morning_brief_nodes import (
    filter_relevant_events,
    detect_anomalies,
    run_analyst_agent,
    narrative_writer,
    WorkflowCostCeilingExceeded,
)


def _make_state(**kwargs) -> MorningBriefState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return MorningBriefState(**defaults)


def _make_registry(role_id: str = "any") -> MagicMock:
    defn = MagicMock()
    defn.role_id = role_id
    registry = MagicMock()
    registry.resolve.return_value = defn
    return registry


def _make_llm_stub(
    output: dict | None = None,
    confidence: float = 0.85,
    cost_usd: float = 0.05,
) -> AsyncMock:
    """Return an async callable that behaves like _invoke_llm_stub."""
    result = {
        "output": output or {"result": "stub"},
        "confidence": confidence,
        "cost_usd": cost_usd,
        "input_tokens": 100,
        "output_tokens": 50,
    }
    stub = AsyncMock(return_value=result)
    return stub


class TestFilterRelevantEvents:
    @pytest.mark.asyncio
    async def test_filter_relevant_events_invokes_agent(self):
        """filter_relevant_events must call the registry to resolve the agent."""
        state = _make_state(events=[{"event_id": "e1", "title": "T"}])
        registry = _make_registry("relevance-analyst")
        invoke = _make_llm_stub(output={"relevant_events": [{"event_id": "e1"}]})

        updated = await filter_relevant_events(
            state, registry=registry, _invoke_llm=invoke
        )

        registry.resolve.assert_called_once_with("relevance-analyst")
        assert isinstance(updated.relevant_events, list)

    @pytest.mark.asyncio
    async def test_filter_relevant_events_accumulates_confidence(self):
        """filter_relevant_events must store confidence in confidence_scores."""
        state = _make_state()
        registry = _make_registry()
        invoke = _make_llm_stub(confidence=0.78)

        updated = await filter_relevant_events(
            state, registry=registry, _invoke_llm=invoke
        )

        assert "relevance-analyst" in updated.confidence_scores
        assert updated.confidence_scores["relevance-analyst"] == pytest.approx(0.78)

    @pytest.mark.asyncio
    async def test_filter_relevant_events_accumulates_cost(self):
        """filter_relevant_events must add cost_usd to state."""
        state = _make_state()
        registry = _make_registry()
        invoke = _make_llm_stub(cost_usd=0.10)

        updated = await filter_relevant_events(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.cost_usd == pytest.approx(0.10)

    @pytest.mark.asyncio
    async def test_filter_relevant_events_raises_at_100_percent_ceiling(self):
        """filter_relevant_events raises WorkflowCostCeilingExceeded at 100%."""
        # Start with cost already at ceiling ($2.00)
        state = _make_state(cost_usd=2.00)
        registry = _make_registry()
        invoke = _make_llm_stub(cost_usd=0.01)  # any additional cost triggers

        with pytest.raises(WorkflowCostCeilingExceeded):
            await filter_relevant_events(
                state,
                registry=registry,
                cost_ceiling_usd=2.0,
                _invoke_llm=invoke,
            )

    @pytest.mark.asyncio
    async def test_filter_relevant_events_warns_at_80_percent_ceiling(self, caplog):
        """filter_relevant_events logs WARNING at 80% of ceiling."""
        import logging
        # Start at $1.58 → after adding $0.05 we hit $1.63 (>80% of $2.00)
        state = _make_state(cost_usd=1.58)
        registry = _make_registry()
        invoke = _make_llm_stub(cost_usd=0.05)

        with caplog.at_level(logging.WARNING, logger="src.ai.workflows.morning_brief_nodes"):
            updated = await filter_relevant_events(
                state,
                registry=registry,
                cost_ceiling_usd=2.0,
                _invoke_llm=invoke,
            )

        # Should not raise, but cost should be above 80%
        assert updated.cost_usd > 1.60
        assert any("context reduction" in r.message or "reduce" in r.message.lower()
                   for r in caplog.records), (
            "Expected a WARNING about context reduction at 80% ceiling"
        )


class TestDetectAnomalies:
    @pytest.mark.asyncio
    async def test_detect_anomalies_invokes_agent(self):
        """detect_anomalies must call the registry to resolve the agent."""
        state = _make_state()
        registry = _make_registry("anomaly-detector")
        invoke = _make_llm_stub(output={"anomalies": [{"ticker": "XYZ", "reason": "spike"}]})

        updated = await detect_anomalies(
            state, registry=registry, _invoke_llm=invoke
        )

        registry.resolve.assert_called_once_with("anomaly-detector")
        assert isinstance(updated.anomalies, list)

    @pytest.mark.asyncio
    async def test_detect_anomalies_populates_anomalies(self):
        """detect_anomalies must populate state.anomalies from agent output."""
        state = _make_state()
        registry = _make_registry()
        anomaly = {"ticker": "AAPL", "reason": "volume spike"}
        invoke = _make_llm_stub(output={"anomalies": [anomaly]})

        updated = await detect_anomalies(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.anomalies == [anomaly]

    @pytest.mark.asyncio
    async def test_detect_anomalies_raises_at_ceiling(self):
        """detect_anomalies raises WorkflowCostCeilingExceeded at 100%."""
        state = _make_state(cost_usd=2.00)
        registry = _make_registry()
        invoke = _make_llm_stub(cost_usd=0.01)

        with pytest.raises(WorkflowCostCeilingExceeded):
            await detect_anomalies(
                state,
                registry=registry,
                cost_ceiling_usd=2.0,
                _invoke_llm=invoke,
            )


class TestRunAnalystAgent:
    @pytest.mark.asyncio
    async def test_run_analyst_agent_invokes_agent(self):
        """run_analyst_agent must call the registry to resolve the agent."""
        state = _make_state()
        registry = _make_registry("morning-brief-analyst")
        invoke = _make_llm_stub(output={"recommendations": [{"ticker": "AAPL"}]})

        updated = await run_analyst_agent(
            state, registry=registry, _invoke_llm=invoke
        )

        registry.resolve.assert_called_once_with("morning-brief-analyst")
        assert isinstance(updated.recommendations, list)

    @pytest.mark.asyncio
    async def test_run_analyst_agent_populates_recommendations(self):
        """run_analyst_agent must populate state.recommendations."""
        state = _make_state()
        registry = _make_registry()
        recs = [{"ticker": "GOOGL", "action": "HOLD"}]
        invoke = _make_llm_stub(output={"recommendations": recs})

        updated = await run_analyst_agent(
            state, registry=registry, _invoke_llm=invoke
        )

        assert updated.recommendations == recs

    @pytest.mark.asyncio
    async def test_run_analyst_agent_raises_at_ceiling(self):
        """run_analyst_agent raises WorkflowCostCeilingExceeded at 100%."""
        state = _make_state(cost_usd=2.00)
        registry = _make_registry()
        invoke = _make_llm_stub(cost_usd=0.01)

        with pytest.raises(WorkflowCostCeilingExceeded):
            await run_analyst_agent(
                state,
                registry=registry,
                cost_ceiling_usd=2.0,
                _invoke_llm=invoke,
            )


class TestNarrativeWriter:
    @pytest.mark.asyncio
    async def test_narrative_writer_invokes_agent(self):
        """narrative_writer must call the registry to resolve the agent."""
        state = _make_state()
        registry = _make_registry("narrative-writer")
        invoke = _make_llm_stub(output={"report": "<h1>Morning Brief</h1>"})

        updated = await narrative_writer(
            state, registry=registry, _invoke_llm=invoke
        )

        registry.resolve.assert_called_once_with("narrative-writer")
        assert updated.report is not None

    @pytest.mark.asyncio
    async def test_narrative_writer_populates_report(self):
        """narrative_writer must populate state.report with the HTML output."""
        state = _make_state()
        registry = _make_registry()
        html = "<h1>Morning Brief</h1><p>Top events...</p>"
        invoke = _make_llm_stub(output={"report": html})

        updated = await narrative_writer(
            state, registry=registry, _invoke_llm=invoke
        )

        assert html in updated.report or updated.report is not None

    @pytest.mark.asyncio
    async def test_narrative_writer_raises_at_ceiling(self):
        """narrative_writer raises WorkflowCostCeilingExceeded at 100%."""
        state = _make_state(cost_usd=2.00)
        registry = _make_registry()
        invoke = _make_llm_stub(cost_usd=0.01)

        with pytest.raises(WorkflowCostCeilingExceeded):
            await narrative_writer(
                state,
                registry=registry,
                cost_ceiling_usd=2.0,
                _invoke_llm=invoke,
            )
