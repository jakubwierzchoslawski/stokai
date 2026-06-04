"""
Unit tests for AgentNode wrappers (5 nodes).

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowType, WorkflowStatus


def _make_state(**kwargs) -> WorkflowState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.ON_DEMAND,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "company_state": {"name": "ACME", "sector": "tech"},
        "active_events": [{"event_id": "e1", "type": "conflict"}],
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


def _make_agent_definition(role_id: str = "exposure-analyst") -> MagicMock:
    defn = MagicMock()
    defn.role_id = role_id
    defn.tools = []
    defn.output_schema = {"type": "object"}
    defn.limits = MagicMock()
    defn.limits.cost_ceiling_usd = 10.0
    defn.limits.max_iterations = 3
    defn.limits.max_input_tokens = 50000
    defn.limits.timeout_seconds = 60
    defn.model = MagicMock()
    defn.model.model_id = "claude-3-5-sonnet-20241022"
    defn.system_prompt_file = "prompts/exposure_analyst.txt"
    return defn


def _make_registry(role_id: str = "exposure-analyst") -> MagicMock:
    registry = MagicMock()
    registry.resolve.return_value = _make_agent_definition(role_id)
    return registry


def _make_llm_result(confidence: float = 0.8) -> dict:
    return {
        "confidence": confidence,
        "cost_usd": 0.01,
        "input_tokens": 100,
        "output_tokens": 50,
        "output": {"summary": "test output"},
    }


class TestExposureAnalystNode:
    @pytest.mark.asyncio
    async def test_exposure_analyst_node_populates_correct_state_field(self):
        from src.ai.workflows.on_demand.nodes.exposure_analyst_node import (
            exposure_analyst_node,
        )

        state = _make_state()
        registry = _make_registry("exposure-analyst")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await exposure_analyst_node(state, registry=registry)

        assert result.exposure_output is not None

    @pytest.mark.asyncio
    async def test_exposure_analyst_node_accumulates_cost(self):
        from src.ai.workflows.on_demand.nodes.exposure_analyst_node import (
            exposure_analyst_node,
        )

        state = _make_state(cost_usd=0.05)
        registry = _make_registry("exposure-analyst")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await exposure_analyst_node(state, registry=registry)

        assert result.cost_usd > 0.05

    @pytest.mark.asyncio
    async def test_exposure_analyst_node_records_confidence_score(self):
        from src.ai.workflows.on_demand.nodes.exposure_analyst_node import (
            exposure_analyst_node,
        )

        state = _make_state()
        registry = _make_registry("exposure-analyst")
        llm_result = _make_llm_result(confidence=0.75)

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await exposure_analyst_node(state, registry=registry)

        assert "exposure-analyst" in result.confidence_scores
        assert result.confidence_scores["exposure-analyst"] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_exposure_analyst_node_raises_on_invalid_output_schema(self):
        from src.ai.workflows.on_demand.nodes.exposure_analyst_node import (
            exposure_analyst_node,
        )

        state = _make_state()
        registry = _make_registry("exposure-analyst")
        # Return None output to trigger schema validation failure
        llm_result = {
            "confidence": 0.8,
            "cost_usd": 0.01,
            "input_tokens": 100,
            "output_tokens": 50,
            "output": None,  # invalid
        }

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            with pytest.raises(Exception):
                await exposure_analyst_node(state, registry=registry)


class TestHistoricalContextNode:
    @pytest.mark.asyncio
    async def test_historical_context_node_populates_correct_state_field(self):
        from src.ai.workflows.on_demand.nodes.historical_context_node import (
            historical_context_node,
        )

        state = _make_state()
        registry = _make_registry("historical-context")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await historical_context_node(state, registry=registry)

        assert result.historical_output is not None

    @pytest.mark.asyncio
    async def test_historical_context_node_accumulates_cost(self):
        from src.ai.workflows.on_demand.nodes.historical_context_node import (
            historical_context_node,
        )

        state = _make_state(cost_usd=0.05)
        registry = _make_registry("historical-context")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await historical_context_node(state, registry=registry)

        assert result.cost_usd > 0.05

    @pytest.mark.asyncio
    async def test_historical_context_node_records_confidence_score(self):
        from src.ai.workflows.on_demand.nodes.historical_context_node import (
            historical_context_node,
        )

        state = _make_state()
        registry = _make_registry("historical-context")
        llm_result = _make_llm_result(confidence=0.82)

        with patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await historical_context_node(state, registry=registry)

        assert "historical-context" in result.confidence_scores

    @pytest.mark.asyncio
    async def test_historical_context_node_raises_on_invalid_output_schema(self):
        from src.ai.workflows.on_demand.nodes.historical_context_node import (
            historical_context_node,
        )

        state = _make_state()
        registry = _make_registry("historical-context")
        llm_result = {
            "confidence": 0.8,
            "cost_usd": 0.01,
            "input_tokens": 100,
            "output_tokens": 50,
            "output": None,
        }

        with patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            with pytest.raises(Exception):
                await historical_context_node(state, registry=registry)

    @pytest.mark.asyncio
    async def test_historical_context_node_parallel_calls_use_asyncio_gather(self):
        """historical_context_node uses asyncio.gather for parallel sub-tasks."""
        from src.ai.workflows.on_demand.nodes.historical_context_node import (
            historical_context_node,
        )
        import asyncio

        state = _make_state()
        registry = _make_registry("historical-context")
        llm_result = _make_llm_result()

        gather_calls = []
        original_gather = asyncio.gather

        async def mock_gather(*coros, **kwargs):
            gather_calls.append(len(coros))
            return await original_gather(*coros, **kwargs)

        with patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            with patch(
                "src.ai.workflows.on_demand.nodes.historical_context_node.asyncio.gather",
                side_effect=mock_gather,
            ):
                result = await historical_context_node(state, registry=registry)

        # asyncio.gather must have been called
        assert len(gather_calls) >= 1


class TestAnomalyDetectorNode:
    @pytest.mark.asyncio
    async def test_anomaly_detector_node_populates_correct_state_field(self):
        from src.ai.workflows.on_demand.nodes.anomaly_detector_node import (
            anomaly_detector_node,
        )

        state = _make_state(
            exposure_output={"risk": "high"},
            historical_output={"analogies": []},
        )
        registry = _make_registry("anomaly-detector")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await anomaly_detector_node(state, registry=registry)

        assert result.anomaly_output is not None

    @pytest.mark.asyncio
    async def test_anomaly_detector_node_accumulates_cost(self):
        from src.ai.workflows.on_demand.nodes.anomaly_detector_node import (
            anomaly_detector_node,
        )

        state = _make_state(cost_usd=0.1)
        registry = _make_registry("anomaly-detector")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await anomaly_detector_node(state, registry=registry)

        assert result.cost_usd > 0.1

    @pytest.mark.asyncio
    async def test_anomaly_detector_node_records_confidence_score(self):
        from src.ai.workflows.on_demand.nodes.anomaly_detector_node import (
            anomaly_detector_node,
        )

        state = _make_state()
        registry = _make_registry("anomaly-detector")
        llm_result = _make_llm_result(confidence=0.9)

        with patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await anomaly_detector_node(state, registry=registry)

        assert "anomaly-detector" in result.confidence_scores

    @pytest.mark.asyncio
    async def test_anomaly_detector_node_raises_on_invalid_output_schema(self):
        from src.ai.workflows.on_demand.nodes.anomaly_detector_node import (
            anomaly_detector_node,
        )

        state = _make_state()
        registry = _make_registry("anomaly-detector")
        llm_result = {
            "confidence": 0.8,
            "cost_usd": 0.01,
            "input_tokens": 100,
            "output_tokens": 50,
            "output": None,
        }

        with patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            with pytest.raises(Exception):
                await anomaly_detector_node(state, registry=registry)


class TestRecommendationNode:
    @pytest.mark.asyncio
    async def test_recommendation_node_populates_correct_state_field(self):
        from src.ai.workflows.on_demand.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state(
            anomaly_output={"anomalies": []},
        )
        registry = _make_registry("recommendation-synthesizer")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await recommendation_node(state, registry=registry)

        assert result.recommendation is not None

    @pytest.mark.asyncio
    async def test_recommendation_node_accumulates_cost(self):
        from src.ai.workflows.on_demand.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state(cost_usd=0.2)
        registry = _make_registry("recommendation-synthesizer")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await recommendation_node(state, registry=registry)

        assert result.cost_usd > 0.2

    @pytest.mark.asyncio
    async def test_recommendation_node_records_confidence_score(self):
        from src.ai.workflows.on_demand.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state()
        registry = _make_registry("recommendation-synthesizer")
        llm_result = _make_llm_result(confidence=0.7)

        with patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await recommendation_node(state, registry=registry)

        assert "recommendation-synthesizer" in result.confidence_scores

    @pytest.mark.asyncio
    async def test_recommendation_node_raises_on_invalid_output_schema(self):
        from src.ai.workflows.on_demand.nodes.recommendation_node import (
            recommendation_node,
        )

        state = _make_state()
        registry = _make_registry("recommendation-synthesizer")
        llm_result = {
            "confidence": 0.8,
            "cost_usd": 0.01,
            "input_tokens": 100,
            "output_tokens": 50,
            "output": None,
        }

        with patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            with pytest.raises(Exception):
                await recommendation_node(state, registry=registry)


class TestNarrativeWriterNode:
    @pytest.mark.asyncio
    async def test_narrative_writer_node_populates_correct_state_field(self):
        from src.ai.workflows.on_demand.nodes.narrative_writer_node import (
            narrative_writer_node,
        )

        state = _make_state(
            recommendation={"action": "hold"},
        )
        registry = _make_registry("narrative-writer")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await narrative_writer_node(state, registry=registry)

        assert result.report is not None

    @pytest.mark.asyncio
    async def test_narrative_writer_node_accumulates_cost(self):
        from src.ai.workflows.on_demand.nodes.narrative_writer_node import (
            narrative_writer_node,
        )

        state = _make_state(cost_usd=0.3)
        registry = _make_registry("narrative-writer")
        llm_result = _make_llm_result()

        with patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await narrative_writer_node(state, registry=registry)

        assert result.cost_usd > 0.3

    @pytest.mark.asyncio
    async def test_narrative_writer_node_records_confidence_score(self):
        from src.ai.workflows.on_demand.nodes.narrative_writer_node import (
            narrative_writer_node,
        )

        state = _make_state()
        registry = _make_registry("narrative-writer")
        llm_result = _make_llm_result(confidence=0.85)

        with patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await narrative_writer_node(state, registry=registry)

        assert "narrative-writer" in result.confidence_scores

    @pytest.mark.asyncio
    async def test_narrative_writer_node_raises_on_invalid_output_schema(self):
        from src.ai.workflows.on_demand.nodes.narrative_writer_node import (
            narrative_writer_node,
        )

        state = _make_state()
        registry = _make_registry("narrative-writer")
        llm_result = {
            "confidence": 0.8,
            "cost_usd": 0.01,
            "input_tokens": 100,
            "output_tokens": 50,
            "output": None,
        }

        with patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            with pytest.raises(Exception):
                await narrative_writer_node(state, registry=registry)
