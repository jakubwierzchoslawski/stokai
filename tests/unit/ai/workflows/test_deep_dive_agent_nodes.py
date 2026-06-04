"""
Unit tests for Event Deep-Dive AgentNode wrappers (PLAN-F-010 TASK-007).

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import (
    DeepDiveWorkflowState,
    ExposureAnalysis,
    GeoEvent,
    MemoDraft,
    PriceReaction,
)
from src.ai.workflows.state import WorkflowType, WorkflowStatus


def _make_state(**kwargs) -> DeepDiveWorkflowState:
    event_id = uuid.uuid4()
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.EVENT_DEEP_DIVE,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "status": WorkflowStatus.RUNNING,
        "inputs": {"event_id": str(event_id)},
        "event_full": GeoEvent(
            event_id=event_id,
            title="Test Event",
            summary="A test event occurred.",
            category=["conflict"],
            intensity=3,
            sentiment=-0.5,
        ),
        "market_reaction": {
            str(uuid.uuid4()): PriceReaction(
                company_id=uuid.uuid4(), ticker="AAPL", change_pct=-0.02
            )
        },
        "exposure_analyses": [
            ExposureAnalysis(
                company_id=uuid.uuid4(),
                exposure_type="direct",
                direction="negative",
                magnitude=0.7,
                reasoning="Test reasoning",
                confidence=0.8,
                cost_usd=0.05,
            )
        ],
    }
    defaults.update(kwargs)
    return DeepDiveWorkflowState(**defaults)


def _make_registry(role_id: str) -> MagicMock:
    defn = MagicMock()
    defn.role_id = role_id
    defn.limits = MagicMock()
    defn.limits.cost_ceiling_usd = 5.0
    defn.limits.max_input_tokens = 50000
    defn.model = MagicMock()
    defn.model.model_id = "claude-3-5-sonnet-20241022"
    registry = MagicMock()
    registry.resolve.return_value = defn
    return registry


def _make_accumulator(ceiling: float = 10.0):
    from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
    return CostAccumulator(ceiling_usd=ceiling)


def _make_llm_result(role_id: str, confidence: float = 0.8) -> dict:
    return {
        "role_id": role_id,
        "confidence": confidence,
        "cost_usd": 0.05,
        "output": {"summary": f"output from {role_id}"},
    }


class TestEventDeepDiveAgent:
    @pytest.mark.asyncio
    async def test_event_deep_dive_agent_updates_state_with_analysis(self):
        from src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent import (
            event_deep_dive_agent,
        )

        state = _make_state()
        registry = _make_registry("event-deep-dive-analyst")
        accumulator = _make_accumulator()

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
            new_callable=AsyncMock,
            return_value=_make_llm_result("event-deep-dive-analyst"),
        ):
            result = await event_deep_dive_agent(
                state, registry=registry, cost_accumulator=accumulator
            )

        assert result.exposure_output is not None or result.confidence_scores.get("event-deep-dive-analyst") is not None

    @pytest.mark.asyncio
    async def test_any_agent_node_propagates_cost_ceiling_exceeded(self):
        from src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent import (
            event_deep_dive_agent,
        )
        from src.ai.workflows.event_deep_dive.exceptions import CostCeilingExceededError

        state = _make_state()
        registry = _make_registry("event-deep-dive-analyst")
        # Use tiny ceiling so it fails
        accumulator = _make_accumulator(ceiling=0.001)

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
            new_callable=AsyncMock,
            return_value=_make_llm_result("event-deep-dive-analyst"),
        ):
            with pytest.raises(CostCeilingExceededError):
                await event_deep_dive_agent(
                    state, registry=registry, cost_accumulator=accumulator
                )

    @pytest.mark.asyncio
    async def test_any_agent_node_updates_confidence_scores(self):
        from src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent import (
            event_deep_dive_agent,
        )

        state = _make_state()
        registry = _make_registry("event-deep-dive-analyst")
        accumulator = _make_accumulator()

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
            new_callable=AsyncMock,
            return_value=_make_llm_result("event-deep-dive-analyst", confidence=0.75),
        ):
            result = await event_deep_dive_agent(
                state, registry=registry, cost_accumulator=accumulator
            )

        assert "event-deep-dive-analyst" in result.confidence_scores
        assert result.confidence_scores["event-deep-dive-analyst"] == pytest.approx(0.75)


class TestHistoricalContextAgent:
    @pytest.mark.asyncio
    async def test_historical_context_agent_updates_analogies(self):
        from src.ai.workflows.event_deep_dive.nodes.historical_context_agent import (
            historical_context_agent,
        )

        state = _make_state()
        registry = _make_registry("historical-context-analyst")
        accumulator = _make_accumulator()

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
            new_callable=AsyncMock,
            return_value=_make_llm_result("historical-context-analyst"),
        ):
            result = await historical_context_agent(
                state, registry=registry, cost_accumulator=accumulator
            )

        # historical_output should be set
        assert result.historical_output is not None


class TestRecommendationSynthesizer:
    @pytest.mark.asyncio
    async def test_recommendation_synthesizer_produces_per_company_recommendations(self):
        from src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer import (
            recommendation_synthesizer,
        )

        state = _make_state()
        registry = _make_registry("recommendation-synthesizer")
        accumulator = _make_accumulator()

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
            new_callable=AsyncMock,
            return_value=_make_llm_result("recommendation-synthesizer"),
        ):
            result = await recommendation_synthesizer(
                state, registry=registry, cost_accumulator=accumulator
            )

        assert result.recommendation is not None


class TestNarrativeWriter:
    @pytest.mark.asyncio
    async def test_narrative_writer_sets_memo_draft(self):
        """narrative_writer MUST set state.memo_draft (last AgentNode invariant)."""
        from src.ai.workflows.event_deep_dive.nodes.narrative_writer import (
            narrative_writer,
        )

        state = _make_state()
        registry = _make_registry("narrative-writer")
        accumulator = _make_accumulator()

        with patch(
            "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
            new_callable=AsyncMock,
            return_value=_make_llm_result("narrative-writer"),
        ):
            result = await narrative_writer(
                state, registry=registry, cost_accumulator=accumulator
            )

        assert result.memo_draft is not None
        assert isinstance(result.memo_draft, MemoDraft)
