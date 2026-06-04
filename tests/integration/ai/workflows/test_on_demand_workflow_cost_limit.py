"""
Integration test: on-demand workflow stops when cost ceiling is exceeded.

Tests that CostCeilingGuard halts workflow execution and the returned
WorkflowState has status=COST_LIMIT.
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


class TestOnDemandWorkflowCostLimit:
    @pytest.mark.asyncio
    async def test_graph_routes_to_cost_limit_when_ceiling_exceeded(self):
        """When cost ceiling is exceeded, status is COST_LIMIT."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()

        # Cost ceiling is 0.05 but each node will cost 0.10 — ceiling exceeded
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=0.05,
            pg_checkpointer=None,
        )

        high_cost_result = {
            "output": {"summary": "test"},
            "confidence": 0.85,
            "cost_usd": 0.10,  # exceeds ceiling immediately
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ):
            result = await graph.ainvoke(state)

        assert result.status == WorkflowStatus.COST_LIMIT

    @pytest.mark.asyncio
    async def test_graph_sets_error_detail_on_cost_limit(self):
        """On cost limit, error_detail is populated with cost information."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()

        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=0.05,
            pg_checkpointer=None,
        )

        high_cost_result = {
            "output": {"summary": "test"},
            "confidence": 0.85,
            "cost_usd": 0.10,
            "input_tokens": 100,
            "output_tokens": 50,
        }

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ), patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=high_cost_result,
        ):
            result = await graph.ainvoke(state)

        assert result.error_detail is not None
