"""
Integration test: on-demand workflow confidence routing.

Tests that evaluate_quality correctly routes to:
  - COMPLETED when overall_confidence >= 0.7
  - HIL_PENDING when 0.4 <= overall_confidence < 0.7
  - BLOCKED when overall_confidence < 0.4
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


def _make_state(**kwargs) -> WorkflowState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.ON_DEMAND,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


def _make_registry() -> MagicMock:
    defn = MagicMock()
    defn.role_id = "exposure-analyst"
    defn.tools = []
    defn.output_schema = {"type": "object"}
    defn.limits = MagicMock()
    defn.limits.cost_ceiling_usd = 10.0
    defn.limits.max_iterations = 3
    defn.limits.max_input_tokens = 50000
    defn.limits.timeout_seconds = 60
    defn.model = MagicMock()
    defn.model.model_id = "claude-3-5-sonnet-20241022"
    defn.system_prompt_file = "prompts/test.txt"

    registry = MagicMock()
    registry.resolve.return_value = defn
    return registry


def _make_llm_result(confidence: float = 0.85) -> dict:
    return {
        "output": {"summary": "test output"},
        "confidence": confidence,
        "cost_usd": 0.01,
        "input_tokens": 100,
        "output_tokens": 50,
    }


class TestConfidenceRouting:
    @pytest.mark.asyncio
    async def test_high_confidence_routes_to_completed(self):
        """All nodes at 0.85 confidence → COMPLETED."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=5.0,
            pg_checkpointer=None,
        )

        llm_result = _make_llm_result(confidence=0.85)
        patch_targets = [
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
        ]

        patches = [
            patch(target, new_callable=AsyncMock, return_value=llm_result)
            for target in patch_targets
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await graph.ainvoke(state)

        assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_mid_confidence_routes_to_hil_pending(self):
        """All nodes at 0.55 confidence → HIL_PENDING."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=5.0,
            pg_checkpointer=None,
        )

        llm_result = _make_llm_result(confidence=0.55)
        patch_targets = [
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
        ]

        patches = [
            patch(target, new_callable=AsyncMock, return_value=llm_result)
            for target in patch_targets
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await graph.ainvoke(state)

        assert result.status == WorkflowStatus.HIL_PENDING
        assert result.requires_hil is True

    @pytest.mark.asyncio
    async def test_low_confidence_routes_to_blocked(self):
        """All nodes at 0.3 confidence → BLOCKED."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=5.0,
            pg_checkpointer=None,
        )

        llm_result = _make_llm_result(confidence=0.30)
        patch_targets = [
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
        ]

        patches = [
            patch(target, new_callable=AsyncMock, return_value=llm_result)
            for target in patch_targets
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await graph.ainvoke(state)

        assert result.status == WorkflowStatus.BLOCKED
