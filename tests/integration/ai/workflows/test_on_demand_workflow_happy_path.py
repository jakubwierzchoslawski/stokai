"""
Integration test: on-demand workflow happy path.

Tests that build_on_demand_graph produces a graph that, when invoked with a
fully-mocked set of agent nodes, returns a WorkflowState with status=COMPLETED
and all output fields populated.

All external dependencies (LLM calls, repos) are stubbed so this test runs
without a real database or LLM.
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


_GOOD_LLM_RESULT = {
    "output": {"summary": "test output", "key": "value"},
    "confidence": 0.85,
    "cost_usd": 0.01,
    "input_tokens": 100,
    "output_tokens": 50,
}


class TestOnDemandWorkflowHappyPath:
    @pytest.mark.asyncio
    async def test_graph_ainvoke_returns_workflowstate(self):
        """Graph.ainvoke with all nodes succeeding returns a WorkflowState."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=5.0,
            pg_checkpointer=None,
        )

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ):
            result = await graph.ainvoke(state)

        assert isinstance(result, WorkflowState)

    @pytest.mark.asyncio
    async def test_graph_ainvoke_populates_all_output_fields(self):
        """All five agent outputs are populated after happy-path execution."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=5.0,
            pg_checkpointer=None,
        )

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ), patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=_GOOD_LLM_RESULT,
        ):
            result = await graph.ainvoke(state)

        assert result.exposure_output is not None
        assert result.historical_output is not None
        assert result.anomaly_output is not None
        assert result.recommendation is not None
        assert result.report is not None

    @pytest.mark.asyncio
    async def test_graph_ainvoke_accumulates_cost(self):
        """cost_usd is accumulated across all nodes after execution."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        state = _make_state()
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=5.0,
            pg_checkpointer=None,
        )

        llm_result_with_cost = {**_GOOD_LLM_RESULT, "cost_usd": 0.10}

        with patch(
            "src.ai.workflows.on_demand.nodes.exposure_analyst_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result_with_cost,
        ), patch(
            "src.ai.workflows.on_demand.nodes.historical_context_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result_with_cost,
        ), patch(
            "src.ai.workflows.on_demand.nodes.anomaly_detector_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result_with_cost,
        ), patch(
            "src.ai.workflows.on_demand.nodes.recommendation_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result_with_cost,
        ), patch(
            "src.ai.workflows.on_demand.nodes.narrative_writer_node._invoke_llm",
            new_callable=AsyncMock,
            return_value=llm_result_with_cost,
        ):
            result = await graph.ainvoke(state)

        # At least 5 nodes × 0.10 (historical has 2 parallel calls so 6 total)
        assert result.cost_usd >= 0.50
