"""
ai.workflows.earnings_brief.workflow — Backward-compat shim.

The canonical implementation is in graph.py (PLAN-F-009 TASK-008).
This module re-exports symbols AND provides legacy invocation functions
that existing integration tests patch via patch.multiple().

PLAN-F-009 TASK-008 (backward-compat shim)
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.earnings_brief.state import EarningsBriefState, ScenarioTree
from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.state import WorkflowStatus

logger = logging.getLogger(__name__)

# Re-export canonical symbols
from src.ai.workflows.earnings_brief.graph import (  # noqa: E402
    EarningsBriefGraph,
    build_earnings_brief_graph,
    node_sequence,
    _NODE_SEQUENCE,
)


# ── Legacy invocation functions (patchable in integration tests) ──────────────
# These are called by the backward-compat EarningsBriefWorkflow (used by tests
# that patch via workflow._invoke_scenario_analyst etc.)


async def _invoke_scenario_analyst(
    state: EarningsBriefState,
    registry: Any,
) -> dict:
    """Invoke the earnings context agent. Patchable in tests."""
    from src.ai.workflows.earnings_brief.nodes.earnings_context_node import (
        _invoke_earnings_context_agent,
    )
    return await _invoke_earnings_context_agent(state, registry)


async def _invoke_recommendation_agent(
    state: EarningsBriefState,
    registry: Any,
) -> dict:
    """Invoke the recommendation synthesizer. Patchable in tests."""
    from src.ai.workflows.earnings_brief.nodes.recommendation_node import (
        _invoke_recommendation_synthesizer,
    )
    return await _invoke_recommendation_synthesizer(state, registry)


async def _invoke_narrative_writer(
    state: EarningsBriefState,
    registry: Any,
) -> dict:
    """Invoke the narrative writer. Patchable in tests."""
    from src.ai.workflows.earnings_brief.nodes.narrative_writer_node import (
        _invoke_narrative_writer as _nw,
    )
    return await _nw(state, registry)


# ── Legacy workflow class (for integration tests) ─────────────────────────────


class _LegacyEarningsBriefWorkflow:
    """Legacy sequential executor used by integration tests that patch invocation functions.

    Calls the module-level _invoke_* functions so patches applied to this
    module take effect.
    """

    def __init__(
        self,
        registry: Any,
        cost_ceiling_usd: float,
    ) -> None:
        self._registry = registry
        self._cost_ceiling_usd = cost_ceiling_usd

    async def ainvoke(
        self,
        state: EarningsBriefState,
        config: Any = None,
    ) -> EarningsBriefState:
        """Execute legacy workflow using module-level invocation functions."""
        from src.ai.workflows.earnings_brief.nodes.context import NodeContext
        from src.ai.workflows.earnings_brief.nodes.fetch_company_state import (
            fetch_company_state,
        )
        from src.ai.workflows.earnings_brief.nodes.fetch_earnings_history import (
            fetch_earnings_history,
        )
        from src.ai.workflows.earnings_brief.nodes.fetch_macro_context import (
            fetch_macro_context,
        )
        from src.ai.workflows.earnings_brief.nodes.fetch_sector_recent_earnings import (
            fetch_sector_recent_earnings,
        )
        from src.ai.workflows.earnings_brief.nodes.evaluate_quality import (
            evaluate_quality,
        )

        cost_guard = CostCeilingGuard(ceiling_usd=self._cost_ceiling_usd)
        ctx = NodeContext()

        try:
            # Fetch nodes
            state = await fetch_company_state(state, ctx)
            state = await fetch_earnings_history(state, ctx)
            state = await fetch_macro_context(state, ctx)
            state = await fetch_sector_recent_earnings(state, ctx)

            # Scenario analyst (via module-level function — patchable)
            result = await _invoke_scenario_analyst(state, self._registry)
            output = result.get("output")
            if output is None:
                raise ValueError("Scenario analyst returned None output")
            scenario_tree = ScenarioTree(**output)
            cost_delta = float(result.get("cost_usd", 0.0))
            confidence = float(result.get("confidence", 0.0))
            new_scores = dict(state.confidence_scores)
            new_scores["scenario_analyst"] = confidence
            state = state.model_copy(update={
                "scenario_tree": scenario_tree,
                "cost_usd": state.cost_usd + cost_delta,
                "confidence_scores": new_scores,
            })
            cost_guard.check(state)

            # Historical context (use node directly — not legacy patched)
            # Note: we do NOT add to confidence_scores here to preserve backward
            # compat with integration tests that only patch the 3 main agents.
            from src.ai.workflows.earnings_brief.nodes.historical_context_node import (
                _invoke_historical_context_agent,
            )
            hist_result = await _invoke_historical_context_agent(state, self._registry)
            hist_output = hist_result.get("output", {})
            state = state.model_copy(update={
                "analogies_output": hist_output,
                "cost_usd": state.cost_usd + float(hist_result.get("cost_usd", 0.0)),
            })
            cost_guard.check(state)

            # Recommendation agent (via module-level function — patchable)
            rec_result = await _invoke_recommendation_agent(state, self._registry)
            rec_output = rec_result.get("output")
            if rec_output is None:
                raise ValueError("Recommendation agent returned None output")
            rec_confidence = float(rec_result.get("confidence", 0.0))
            new_scores = dict(state.confidence_scores)
            new_scores["recommendation_agent"] = rec_confidence
            state = state.model_copy(update={
                "recommendation": rec_output,
                "cost_usd": state.cost_usd + float(rec_result.get("cost_usd", 0.0)),
                "confidence_scores": new_scores,
            })
            cost_guard.check(state)

            # Narrative writer (via module-level function — patchable)
            narr_result = await _invoke_narrative_writer(state, self._registry)
            narr_output = narr_result.get("output")
            if narr_output is None:
                raise ValueError("Narrative writer returned None output")
            narr_confidence = float(narr_result.get("confidence", 0.0))
            new_scores = dict(state.confidence_scores)
            new_scores["narrative_writer"] = narr_confidence
            state = state.model_copy(update={
                "report": narr_output,
                "cost_usd": state.cost_usd + float(narr_result.get("cost_usd", 0.0)),
                "confidence_scores": new_scores,
            })
            cost_guard.check(state)

            # evaluate_quality (last node)
            state = evaluate_quality(state)

        except WorkflowCostLimitError:
            logger.warning(
                "_LegacyEarningsBriefWorkflow: cost ceiling exceeded: workflow_id=%s",
                state.workflow_id,
            )
            raise

        return state


# Legacy alias — used by unit tests that construct EarningsBriefWorkflow directly
EarningsBriefWorkflow = _LegacyEarningsBriefWorkflow


def build_earnings_brief_workflow(
    registry: Any,
    cost_ceiling_usd: float,
) -> _LegacyEarningsBriefWorkflow:
    """Build backward-compatible workflow that uses module-level invocation functions.

    Integration tests that use patch.multiple('...workflow', ...) should use this.

    Args:
        registry: IAgentRegistry implementation.
        cost_ceiling_usd: Per-run cost ceiling in USD.

    Returns:
        _LegacyEarningsBriefWorkflow for ainvoke().
    """
    from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator

    # Validate the sequence (using validator convention)
    validation_sequence = _NODE_SEQUENCE[:-2] + ["evaluate_quality", "narrative_writer"]
    WorkflowStructureValidator().validate(validation_sequence)

    return _LegacyEarningsBriefWorkflow(
        registry=registry,
        cost_ceiling_usd=cost_ceiling_usd,
    )


__all__ = [
    "EarningsBriefGraph",
    "EarningsBriefWorkflow",
    "_LegacyEarningsBriefWorkflow",
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
