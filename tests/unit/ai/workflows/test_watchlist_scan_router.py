"""
Unit tests for route_after_quality and graph assembly.

TDD: written before implementation — PLAN-F-008 TASK-012.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.watchlist_scan.router import route_after_quality
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


# ── route_after_quality ───────────────────────────────────────────────────────


class TestRouteAfterQuality:
    def test_router_returns_dispatch_above_threshold(self):
        """overall_confidence=0.80 → 'dispatch'."""
        state = _make_state(overall_confidence=0.80)
        assert route_after_quality(state) == "dispatch"

    def test_router_returns_hil_in_mid_range(self):
        """overall_confidence=0.55 → 'hil_enqueue'."""
        state = _make_state(overall_confidence=0.55)
        assert route_after_quality(state) == "hil_enqueue"

    def test_router_returns_block_below_threshold(self):
        """overall_confidence=0.30 → 'block_and_notify'."""
        state = _make_state(overall_confidence=0.30)
        assert route_after_quality(state) == "block_and_notify"

    def test_router_boundary_at_0_70_is_dispatch(self):
        """overall_confidence=0.70 → 'dispatch' (inclusive)."""
        state = _make_state(overall_confidence=0.70)
        assert route_after_quality(state) == "dispatch"

    def test_router_boundary_at_0_40_is_hil(self):
        """overall_confidence=0.40 → 'hil_enqueue' (inclusive)."""
        state = _make_state(overall_confidence=0.40)
        assert route_after_quality(state) == "hil_enqueue"

    def test_router_just_below_0_70_is_hil(self):
        """overall_confidence=0.699 → 'hil_enqueue'."""
        state = _make_state(overall_confidence=0.699)
        assert route_after_quality(state) == "hil_enqueue"

    def test_router_just_below_0_40_is_block(self):
        """overall_confidence=0.399 → 'block_and_notify'."""
        state = _make_state(overall_confidence=0.399)
        assert route_after_quality(state) == "block_and_notify"

    def test_router_zero_confidence_is_block(self):
        """overall_confidence=0.0 → 'block_and_notify'."""
        state = _make_state(overall_confidence=0.0)
        assert route_after_quality(state) == "block_and_notify"

    def test_router_full_confidence_is_dispatch(self):
        """overall_confidence=1.0 → 'dispatch'."""
        state = _make_state(overall_confidence=1.0)
        assert route_after_quality(state) == "dispatch"


# ── Graph assembly ────────────────────────────────────────────────────────────


class TestBuildWatchlistScanGraph:
    def _make_registry(self) -> MagicMock:
        definition = AsyncMock()
        definition.ainvoke = AsyncMock(return_value={
            "relevant_events": [],
            "anomalies": [],
            "recommendations": [],
            "report": {"content": "<p>ok</p>"},
            "cost_usd": 0.01,
            "confidence": 0.85,
        })
        registry = MagicMock()
        registry.resolve = MagicMock(return_value=definition)
        return registry

    def _make_tool_library(self) -> AsyncMock:
        tl = AsyncMock()
        tl.get_watchlist = AsyncMock(return_value=[uuid.uuid4()])
        tl.get_portfolio_state = AsyncMock(return_value=[])
        tl.query_recent_events = AsyncMock(return_value=[])
        tl.get_company_score_history = AsyncMock(
            return_value={"prior_score": 0.5, "current_score": 0.6}
        )
        return tl

    def test_graph_node_order_enforces_narrative_writer_before_evaluate_quality(self):
        """Graph structure test: narrative_writer index < evaluate_quality index."""
        from src.ai.workflows.watchlist_scan.graph import _NODE_SEQUENCE

        nw_idx = _NODE_SEQUENCE.index("narrative_writer")
        eq_idx = _NODE_SEQUENCE.index("evaluate_quality")
        assert nw_idx < eq_idx

    def test_graph_has_all_required_nodes(self):
        """All expected nodes present in _NODE_SEQUENCE."""
        from src.ai.workflows.watchlist_scan.graph import _NODE_SEQUENCE

        required = [
            "fetch_watchlist",
            "fetch_today_events",
            "relevance_analyst",
            "recompute_scores",
            "anomaly_detector",
            "historical_context_agent",
            "recommendation_synthesizer",
            "narrative_writer",
            "evaluate_quality",
        ]
        for node in required:
            assert node in _NODE_SEQUENCE, f"Node '{node}' missing from _NODE_SEQUENCE"

    def test_graph_conditional_branch_wires_all_three_outcomes(self):
        """route_after_quality can return all three branch names."""
        dispatch_state = _make_state(overall_confidence=0.80)
        hil_state = _make_state(overall_confidence=0.55)
        block_state = _make_state(overall_confidence=0.20)

        assert route_after_quality(dispatch_state) == "dispatch"
        assert route_after_quality(hil_state) == "hil_enqueue"
        assert route_after_quality(block_state) == "block_and_notify"

    def test_build_watchlist_scan_graph_returns_graph_instance(self):
        """build_watchlist_scan_graph returns an object with ainvoke()."""
        from src.ai.workflows.watchlist_scan.graph import build_watchlist_scan_graph

        registry = self._make_registry()
        tool_library = self._make_tool_library()
        graph = build_watchlist_scan_graph(
            registry=registry,
            tool_library=tool_library,
            cost_ceiling_usd=1.00,
        )

        assert hasattr(graph, "ainvoke")

    def test_graph_has_postgresql_checkpointer_in_prod_config(self):
        """Graph accepts and stores pg_checkpointer when provided."""
        from src.ai.workflows.watchlist_scan.graph import build_watchlist_scan_graph

        registry = self._make_registry()
        tool_library = self._make_tool_library()
        pg_mock = MagicMock()

        graph = build_watchlist_scan_graph(
            registry=registry,
            tool_library=tool_library,
            cost_ceiling_usd=1.00,
            pg_checkpointer=pg_mock,
        )

        assert graph._pg_checkpointer is pg_mock
