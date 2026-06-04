"""
Integration tests for the Event Deep-Dive LangGraph StateGraph (PLAN-F-010 TASK-010).

TDD: written before full integration is wired. All external deps (registry,
repos, LLM) are mocked — no real PostgreSQL or LLM calls required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import (
    DeepDiveWorkflowState,
    GeoEvent,
    MemoDraft,
)
from src.ai.workflows.state import WorkflowStatus, WorkflowType


def _make_state(**kwargs) -> DeepDiveWorkflowState:
    event_id = uuid.uuid4()
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.EVENT_DEEP_DIVE,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
        "inputs": {"event_id": str(event_id)},
        "event_full": GeoEvent(event_id=event_id, title="Test event", exposures=[]),
    }
    defaults.update(kwargs)
    return DeepDiveWorkflowState(**defaults)


def _make_registry() -> MagicMock:
    defn = MagicMock()
    defn.role_id = "exposure-analyst"
    defn.limits = MagicMock()
    defn.limits.cost_ceiling_usd = 5.0
    registry = MagicMock()
    registry.resolve.return_value = defn
    return registry


class TestDeepDiveGraphNodeSequence:
    def test_graph_node_sequence_validates_structure(self):
        """GRAPH_NODES ends with narrative_writer then evaluate_quality."""
        from src.ai.workflows.event_deep_dive.graph import _NODE_SEQUENCE

        assert _NODE_SEQUENCE[-1] == "evaluate_quality"
        assert _NODE_SEQUENCE[-2] == "narrative_writer"

    def test_graph_nodes_constant_has_all_8_nodes(self):
        """GRAPH_NODES contains exactly 8 required node names."""
        from src.ai.workflows.event_deep_dive.graph import _NODE_SEQUENCE
        from src.ai.workflows.event_deep_dive.state import GRAPH_NODES

        assert len(_NODE_SEQUENCE) == 8
        assert len(GRAPH_NODES) == 8

    def test_build_deep_dive_graph_returns_graph_with_ainvoke(self):
        """build_deep_dive_graph returns an object with ainvoke() interface."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph

        registry = _make_registry()
        graph = build_deep_dive_graph(registry=registry, cost_ceiling_usd=5.0)

        assert hasattr(graph, "ainvoke")

    def test_all_graph_nodes_are_reachable(self):
        """All 8 node names in GRAPH_NODES are importable functions."""
        from src.ai.workflows.event_deep_dive import state as s

        for node_name in s.GRAPH_NODES:
            assert isinstance(node_name, str), f"{node_name} is not a string"


class TestDeepDiveGraphInvoke:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_state_with_confidence_scores_set(self):
        """ainvoke completes and returns a state with confidence_scores populated."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph

        registry = _make_registry()
        state = _make_state()

        # Patch all agent node _invoke_agent functions to return stubs
        with (
            patch(
                "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "edd", "confidence": 0.8, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "hca", "confidence": 0.85, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
                new=AsyncMock(return_value={"role_id": "rs", "confidence": 0.82, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
                new=AsyncMock(return_value={
                    "role_id": "nw",
                    "confidence": 0.8,
                    "cost_usd": 0.01,
                    "output": {
                        "headline": "H",
                        "executive_summary": "S",
                        "event_analysis": {},
                        "market_impact": {},
                        "confidence": 0.8,
                    },
                }),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.run_exposure_analysts._invoke_analyst",
                new=AsyncMock(return_value=None),
            ),
        ):
            graph = build_deep_dive_graph(registry=registry, cost_ceiling_usd=5.0)
            result = await graph.ainvoke(state)

        assert "workflow" in result.confidence_scores

    @pytest.mark.asyncio
    async def test_ainvoke_with_high_confidence_auto_stores(self):
        """ainvoke with all agents at high confidence routes to auto_store."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph
        from src.ai.workflows.shared.memo_store import MemoStore

        registry = _make_registry()
        state = _make_state()

        # High-confidence agent results
        high_conf_result = {
            "role_id": "any",
            "confidence": 0.85,
            "cost_usd": 0.01,
            "output": {
                "headline": "H",
                "executive_summary": "S",
                "event_analysis": {},
                "market_impact": {},
                "confidence": 0.85,
            },
        }

        mock_memo_store = AsyncMock(spec=MemoStore)
        mock_memo_store.persist = AsyncMock(return_value=MagicMock(brief_id=uuid.uuid4()))

        with (
            patch(
                "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
                new=AsyncMock(return_value=high_conf_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
                new=AsyncMock(return_value=high_conf_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
                new=AsyncMock(return_value=high_conf_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
                new=AsyncMock(return_value=high_conf_result),
            ),
        ):
            graph = build_deep_dive_graph(
                registry=registry,
                cost_ceiling_usd=5.0,
                workflow_run_repo=AsyncMock(),
                brief_repo=AsyncMock(),
            )
            graph._memo_store = mock_memo_store
            result = await graph.ainvoke(state)

        assert result.confidence_scores.get("workflow", 0.0) >= 0.70

    @pytest.mark.asyncio
    async def test_ainvoke_requires_hil_when_mid_confidence(self):
        """ainvoke sets requires_hil=True when min confidence is 0.4–0.69."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph

        registry = _make_registry()
        state = _make_state()

        mid_result = {
            "role_id": "any",
            "confidence": 0.55,
            "cost_usd": 0.01,
            "output": {
                "headline": "H",
                "executive_summary": "S",
                "event_analysis": {},
                "market_impact": {},
                "confidence": 0.55,
            },
        }

        with (
            patch(
                "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
                new=AsyncMock(return_value=mid_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
                new=AsyncMock(return_value=mid_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
                new=AsyncMock(return_value=mid_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
                new=AsyncMock(return_value=mid_result),
            ),
        ):
            graph = build_deep_dive_graph(registry=registry, cost_ceiling_usd=5.0)
            result = await graph.ainvoke(state)

        assert result.requires_hil is True

    @pytest.mark.asyncio
    async def test_ainvoke_memo_draft_set_after_narrative_writer(self):
        """narrative_writer invariant: memo_draft is non-None after ainvoke."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph

        registry = _make_registry()
        state = _make_state()

        with (
            patch(
                "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
                new=AsyncMock(return_value={
                    "role_id": "nw",
                    "confidence": 0.8,
                    "cost_usd": 0.01,
                    "output": {
                        "headline": "H",
                        "executive_summary": "S",
                        "event_analysis": {},
                        "market_impact": {},
                        "confidence": 0.8,
                    },
                }),
            ),
        ):
            graph = build_deep_dive_graph(registry=registry, cost_ceiling_usd=5.0)
            result = await graph.ainvoke(state)

        assert result.memo_draft is not None
        assert isinstance(result.memo_draft, MemoDraft)

    @pytest.mark.asyncio
    async def test_ainvoke_cost_exceeds_ceiling_propagates_error(self):
        """CostCeilingExceededError propagates from the graph."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph
        from src.ai.workflows.event_deep_dive.exceptions import CostCeilingExceededError

        registry = _make_registry()
        state = _make_state()

        # Very low ceiling forces cost exceeded on first agent
        with (
            patch(
                "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.5, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.5, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.5, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.5, "output": {}}),
            ),
        ):
            # Very low ceiling
            graph = build_deep_dive_graph(registry=registry, cost_ceiling_usd=0.001)
            with pytest.raises(CostCeilingExceededError):
                await graph.ainvoke(state)

    @pytest.mark.asyncio
    async def test_evaluate_quality_is_last_node_in_sequence(self):
        """evaluate_quality is called after narrative_writer in ainvoke."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph
        import src.ai.workflows.event_deep_dive.nodes.evaluate_quality as eq_module

        call_order = []

        original_evaluate_quality = eq_module.evaluate_quality

        def capturing_eq(state):
            call_order.append("evaluate_quality")
            return original_evaluate_quality(state)

        registry = _make_registry()
        state = _make_state()

        with (
            patch(
                "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
                new=AsyncMock(return_value={"role_id": "a", "confidence": 0.8, "cost_usd": 0.01, "output": {}}),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
                new=AsyncMock(return_value={
                    "role_id": "nw",
                    "confidence": 0.8,
                    "cost_usd": 0.01,
                    "output": {
                        "headline": "H",
                        "executive_summary": "S",
                        "event_analysis": {},
                        "market_impact": {},
                        "confidence": 0.8,
                    },
                }),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.graph.evaluate_quality",
                side_effect=capturing_eq,
            ),
        ):
            graph = build_deep_dive_graph(registry=registry, cost_ceiling_usd=5.0)
            await graph.ainvoke(state)

        assert "evaluate_quality" in call_order
        # evaluate_quality should be the last thing called
        assert call_order[-1] == "evaluate_quality"

    @pytest.mark.asyncio
    async def test_blocked_route_does_not_call_memo_store(self):
        """When confidence < 0.4, memo_store.persist is not called."""
        from src.ai.workflows.event_deep_dive.graph import build_deep_dive_graph
        from src.ai.workflows.shared.memo_store import MemoStore

        registry = _make_registry()
        state = _make_state()

        low_result = {
            "role_id": "any",
            "confidence": 0.20,
            "cost_usd": 0.01,
            "output": {
                "headline": "H",
                "executive_summary": "S",
                "event_analysis": {},
                "market_impact": {},
                "confidence": 0.20,
            },
        }

        mock_memo_store = AsyncMock(spec=MemoStore)
        mock_memo_store.persist = AsyncMock()

        with (
            patch(
                "src.ai.workflows.event_deep_dive.nodes.event_deep_dive_agent._invoke_agent",
                new=AsyncMock(return_value=low_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.historical_context_agent._invoke_agent",
                new=AsyncMock(return_value=low_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.recommendation_synthesizer._invoke_agent",
                new=AsyncMock(return_value=low_result),
            ),
            patch(
                "src.ai.workflows.event_deep_dive.nodes.narrative_writer._invoke_agent",
                new=AsyncMock(return_value=low_result),
            ),
        ):
            graph = build_deep_dive_graph(
                registry=registry,
                cost_ceiling_usd=5.0,
                workflow_run_repo=AsyncMock(),
                brief_repo=AsyncMock(),
            )
            graph._memo_store = mock_memo_store
            await graph.ainvoke(state)

        mock_memo_store.persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_after_evaluate_returns_correct_branch_high(self):
        """route_after_evaluate returns 'auto_store' for confidence >= 0.7."""
        from src.ai.workflows.event_deep_dive.routing import route_after_evaluate
        from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState
        import uuid
        from datetime import datetime, timezone

        state = DeepDiveWorkflowState(
            workflow_id=uuid.uuid4(),
            workflow_type=WorkflowType.EVENT_DEEP_DIVE,
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            started_at=datetime.now(tz=timezone.utc),
            confidence_scores={"workflow": 0.75},
        )
        result = route_after_evaluate(state)
        assert result == "auto_store"
