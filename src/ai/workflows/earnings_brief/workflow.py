"""
ai.workflows.earnings_brief.workflow — Backward-compat re-export of graph.py.

The canonical implementation is in graph.py (PLAN-F-009 TASK-008).
This module re-exports the key symbols so that existing references continue
to work.

PLAN-F-009 TASK-008 (refactored)
"""
from __future__ import annotations

# Re-export canonical symbols from graph.py
from src.ai.workflows.earnings_brief.graph import (
    EarningsBriefGraph,
    EarningsBriefGraph as EarningsBriefWorkflow,  # legacy alias
    build_earnings_brief_graph,
    build_earnings_brief_graph as build_earnings_brief_workflow,  # legacy alias
    node_sequence,
    _NODE_SEQUENCE,
)
from src.ai.workflows.earnings_brief.state import EarningsBriefState, ScenarioTree

# Re-export node invocation hooks for integration tests that patch via this module
from src.ai.workflows.earnings_brief.nodes.earnings_context_node import (
    _invoke_earnings_context_agent as _invoke_scenario_analyst,
)
from src.ai.workflows.earnings_brief.nodes.recommendation_node import (
    _invoke_recommendation_synthesizer as _invoke_recommendation_agent,
)
from src.ai.workflows.earnings_brief.nodes.narrative_writer_node import (
    _invoke_narrative_writer,
)

__all__ = [
    "EarningsBriefGraph",
    "EarningsBriefWorkflow",
    "build_earnings_brief_graph",
    "build_earnings_brief_workflow",
    "node_sequence",
    "_NODE_SEQUENCE",
    "EarningsBriefState",
    "ScenarioTree",
    "_invoke_scenario_analyst",
    "_invoke_recommendation_agent",
    "_invoke_narrative_writer",
]
