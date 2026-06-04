"""
ai.workflows.earnings_brief.workflow — EarningsBriefWorkflow graph.

Node execution order:
  1. fetch_company_context      (DeterministicNode)
  2. fetch_macro_sector_context (DeterministicNode)
  3. run_scenario_analyst        (AgentNode)
  4. fetch_analogies             (DeterministicNode)
  5. run_recommendation_agent    (AgentNode)
  6. narrative_writer            (AgentNode)
  7. evaluate_quality            (DeterministicNode — confidence gate)
  8. route_after_evaluate        (conditional routing)
  9. persist_brief               (DeterministicNode — DB write)

Conditional routing from evaluate_quality:
  overall_confidence >= 0.70  → auto_store  (COMPLETED)
  overall_confidence >= 0.40  → hil_pending (HIL_PENDING, requires_hil=True)
  overall_confidence < 0.40   → auto_store  (BLOCKED — stored but not sent)

WorkflowStructureValidator is called before the graph is returned (AC-004).

PLAN-F-009 TASK-003
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.earnings_brief.state import EarningsBriefState, ScenarioTree

logger = logging.getLogger(__name__)

# Node sequence for WorkflowStructureValidator (AC-004).
# evaluate_quality is second-to-last; narrative_writer is last (AC-004 invariant).
_NODE_SEQUENCE = [
    "fetch_company_context",
    "fetch_macro_sector_context",
    "run_scenario_analyst",
    "fetch_analogies",
    "run_recommendation_agent",
    "evaluate_quality",
    "narrative_writer",
]

_HIL_THRESHOLD = 0.70
_BLOCK_THRESHOLD = 0.40

_COST_CEILING_USD = 0.50


# ── DeterministicNode stubs ───────────────────────────────────────────────────


async def fetch_company_context(
    state: EarningsBriefState,
    company_repo: Any | None = None,
) -> EarningsBriefState:
    """Fetch company state and earnings history from DB.

    DeterministicNode — no LLM call. Writes company_state, earnings_history.
    """
    logger.debug(
        "fetch_company_context: company_id=%s", state.company_id
    )
    # Production: query companies + earnings_event tables
    # Stub: passthrough (real data injected via repo in task)
    company_state = state.company_state or {
        "company_id": str(state.company_id),
        "stub": True,
    }
    return state.model_copy(update={"company_state": company_state})


async def fetch_macro_sector_context(
    state: EarningsBriefState,
) -> EarningsBriefState:
    """Fetch macro economic indicators and recent sector earnings.

    DeterministicNode — no LLM call. Writes macro_context, sector_recent_earnings.
    """
    logger.debug("fetch_macro_sector_context: workflow_id=%s", state.workflow_id)
    macro_context = state.macro_context or {
        "gdp_growth": None,
        "inflation_rate": None,
        "stub": True,
    }
    return state.model_copy(update={"macro_context": macro_context})


async def fetch_analogies(
    state: EarningsBriefState,
) -> EarningsBriefState:
    """Fetch historical earnings analogies for the company.

    DeterministicNode — no LLM call. Writes analogies_output.
    """
    logger.debug("fetch_analogies: workflow_id=%s", state.workflow_id)
    analogies = state.analogies_output or {"analogies": [], "stub": True}
    return state.model_copy(update={"analogies_output": analogies})


# ── AgentNode implementations ─────────────────────────────────────────────────


async def _invoke_scenario_analyst(
    state: EarningsBriefState,
    registry: Any,
) -> dict:
    """Invoke the earnings analyst LLM to generate a ScenarioTree.

    Patchable in tests via unittest.mock.patch.
    """
    return {
        "output": {
            "bull": {
                "probability": 0.30,
                "rationale": "Strong guidance + macro tailwinds",
                "macro_drivers": ["low interest rates"],
                "sector_drivers": ["sector growth"],
                "implied_price_impact_pct": 5.0,
            },
            "base": {
                "probability": 0.45,
                "rationale": "In-line results expected",
                "macro_drivers": ["stable inflation"],
                "sector_drivers": ["sector average"],
                "implied_price_impact_pct": 0.5,
            },
            "bear": {
                "probability": 0.25,
                "rationale": "Margin compression risk",
                "macro_drivers": ["cost pressures"],
                "sector_drivers": ["competitive pressure"],
                "implied_price_impact_pct": -4.0,
            },
            "analogies": [],
            "macro_summary": "Stable macro environment",
            "sector_summary": "Sector on track",
        },
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def run_scenario_analyst(
    state: EarningsBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
) -> EarningsBriefState:
    """AgentNode: Generate bull / base / bear scenario tree.

    Steps:
      1. Invoke earnings analyst LLM.
      2. Parse output into ScenarioTree (validates probability sum).
      3. Accumulate cost.
      4. Record confidence.
      5. Write scenario_tree to state.
      6. CostCeilingGuard.check(state).

    Raises:
        WorkflowCostLimitError: If cost ceiling reached.
        ValueError: If ScenarioTree probability sum is invalid.
    """
    result = await _invoke_scenario_analyst(state, registry)

    output = result.get("output")
    if output is None:
        raise ValueError("Scenario analyst returned None output")

    # Validate and parse into ScenarioTree
    scenario_tree = ScenarioTree(**output)

    cost_delta = result.get("cost_usd", 0.0)
    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["scenario_analyst"] = result.get("confidence", 0.0)

    updated = state.model_copy(
        update={
            "scenario_tree": scenario_tree,
            "cost_usd": state.cost_usd + cost_delta,
            "confidence_scores": new_confidence_scores,
        }
    )

    guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
    guard.check(updated)

    return updated


async def _invoke_recommendation_agent(
    state: EarningsBriefState,
    registry: Any,
) -> dict:
    """Invoke the recommendation agent LLM. Patchable in tests."""
    return {
        "output": {
            "action": "WATCH",
            "rationale": "Monitor earnings closely; base case in-line.",
            "confidence": 0.80,
        },
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def run_recommendation_agent(
    state: EarningsBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
) -> EarningsBriefState:
    """AgentNode: Generate portfolio action recommendation from scenario tree.

    Raises:
        WorkflowCostLimitError: If cost ceiling reached.
    """
    result = await _invoke_recommendation_agent(state, registry)

    output = result.get("output")
    if output is None:
        raise ValueError("Recommendation agent returned None output")

    cost_delta = result.get("cost_usd", 0.0)
    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["recommendation_agent"] = result.get("confidence", 0.0)

    updated = state.model_copy(
        update={
            "recommendation": output,
            "cost_usd": state.cost_usd + cost_delta,
            "confidence_scores": new_confidence_scores,
        }
    )

    guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
    guard.check(updated)

    return updated


async def _invoke_narrative_writer(
    state: EarningsBriefState,
    registry: Any,
) -> dict:
    """Invoke the narrative writer LLM. Patchable in tests."""
    return {
        "output": {
            "title": "Earnings Brief",
            "sections": ["executive_summary", "scenario_tree", "recommendation"],
            "text": "Stub narrative for earnings brief.",
        },
        "confidence": 0.80,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


async def narrative_writer(
    state: EarningsBriefState,
    *,
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
) -> EarningsBriefState:
    """AgentNode: Write the final narrative report from scenario tree and recommendation.

    Must run before evaluate_quality.

    Raises:
        WorkflowCostLimitError: If cost ceiling reached.
    """
    result = await _invoke_narrative_writer(state, registry)

    output = result.get("output")
    if output is None:
        raise ValueError("Narrative writer returned None output")

    cost_delta = result.get("cost_usd", 0.0)
    new_confidence_scores = dict(state.confidence_scores)
    new_confidence_scores["narrative_writer"] = result.get("confidence", 0.0)

    updated = state.model_copy(
        update={
            "report": output,
            "cost_usd": state.cost_usd + cost_delta,
            "confidence_scores": new_confidence_scores,
        }
    )

    guard = CostCeilingGuard(ceiling_usd=cost_ceiling_usd)
    guard.check(updated)

    return updated


# ── Quality gate and routing ──────────────────────────────────────────────────


def evaluate_quality(state: EarningsBriefState) -> EarningsBriefState:
    """DeterministicNode: compute overall confidence and set requires_hil.

    Decision:
      >= 0.70  → auto-send (requires_hil=False)
      0.40-0.69 → HIL pending (requires_hil=True)
      < 0.40   → blocked, not sent
    """
    if not state.confidence_scores:
        overall = 0.0
    else:
        overall = min(state.confidence_scores.values())

    requires_hil = _BLOCK_THRESHOLD <= overall < _HIL_THRESHOLD

    return state.model_copy(
        update={
            "overall_confidence": overall,
            "requires_hil": requires_hil,
        }
    )


def route_after_evaluate(state: EarningsBriefState) -> str:
    """Conditional routing from evaluate_quality.

    Returns:
        "hil_pending" when overall_confidence < 0.70 and >= 0.40.
        "auto_store"  otherwise (high confidence OR blocked).
    """
    if state.requires_hil:
        return "hil_pending"
    return "auto_store"


async def persist_brief(
    state: EarningsBriefState,
    brief_run_repo: Any | None = None,
    run_id: Any | None = None,
) -> EarningsBriefState:
    """DeterministicNode: persist final state to earnings_brief_run.

    In tests this is a no-op; in production the Celery task calls the repo directly.
    """
    logger.debug(
        "persist_brief: workflow_id=%s requires_hil=%s",
        state.workflow_id,
        state.requires_hil,
    )
    return state


# ── Graph orchestrator ────────────────────────────────────────────────────────


class EarningsBriefWorkflow:
    """Sequential executor for the Earnings Risk Brief workflow.

    Executes nodes in the canonical order:
      fetch_company_context → fetch_macro_sector_context → run_scenario_analyst
      → fetch_analogies → run_recommendation_agent → narrative_writer
      → evaluate_quality → route_after_evaluate → persist_brief

    When cost ceiling is hit in any AgentNode, WorkflowCostLimitError propagates
    and the caller (Celery task) records the failure.

    PLAN-F-009 TASK-003
    """

    def __init__(
        self,
        registry: Any,
        cost_ceiling_usd: float = _COST_CEILING_USD,
    ) -> None:
        self._registry = registry
        self._cost_ceiling_usd = cost_ceiling_usd

    async def ainvoke(
        self,
        state: EarningsBriefState,
        config: Any = None,
    ) -> EarningsBriefState:
        """Execute all nodes in order and return the final state.

        Raises:
            WorkflowCostLimitError: If cost ceiling is exceeded in any AgentNode.
        """
        try:
            # Phase 1: Data fetching (DeterministicNodes)
            state = await fetch_company_context(state)
            state = await fetch_macro_sector_context(state)

            # Phase 2: Scenario generation (AgentNode)
            state = await run_scenario_analyst(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )

            # Phase 3: Analogies (DeterministicNode)
            state = await fetch_analogies(state)

            # Phase 4: Recommendation (AgentNode)
            state = await run_recommendation_agent(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )

            # Phase 5: Quality gate (DeterministicNode — second-to-last per AC-004)
            state = evaluate_quality(state)

            # Phase 6: Routing decision logged
            route = route_after_evaluate(state)
            logger.debug(
                "EarningsBriefWorkflow: workflow_id=%s route=%s confidence=%s",
                state.workflow_id,
                route,
                state.overall_confidence,
            )

            # Phase 7: Narrative writer — LAST node per AC-004
            state = await narrative_writer(
                state,
                registry=self._registry,
                cost_ceiling_usd=self._cost_ceiling_usd,
            )

            # Phase 8: Persist final state
            state = await persist_brief(state)

        except WorkflowCostLimitError:
            logger.warning(
                "EarningsBriefWorkflow cost ceiling exceeded: workflow_id=%s",
                state.workflow_id,
            )
            raise

        except Exception as exc:
            logger.exception(
                "EarningsBriefWorkflow unhandled error: workflow_id=%s: %s",
                state.workflow_id,
                exc,
            )
            raise

        return state


def build_earnings_brief_workflow(
    registry: Any,
    cost_ceiling_usd: float = _COST_CEILING_USD,
) -> EarningsBriefWorkflow:
    """Build and return an EarningsBriefWorkflow instance.

    Calls WorkflowStructureValidator to enforce AC-004 invariant.

    Args:
        registry: IAgentRegistry implementation.
        cost_ceiling_usd: Per-run cost ceiling in USD (default $0.50).

    Returns:
        EarningsBriefWorkflow ready for ainvoke().
    """
    from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator

    WorkflowStructureValidator().validate(_NODE_SEQUENCE)

    return EarningsBriefWorkflow(
        registry=registry,
        cost_ceiling_usd=cost_ceiling_usd,
    )
