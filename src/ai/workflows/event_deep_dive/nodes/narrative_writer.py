"""
ai.workflows.event_deep_dive.nodes.narrative_writer — AgentNode (last AgentNode).

Invokes the narrative-writer agent to produce the final MemoDraft.
This is the LAST AgentNode in the workflow — it MUST set state.memo_draft.

Invariant: memo_draft is non-None after this node completes successfully.

PLAN-F-010 TASK-007.
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState, MemoDraft

logger = logging.getLogger(__name__)

_ROLE_ID = "narrative-writer"


async def _invoke_agent(
    role_id: str,
    definition: Any,
    input_payload: dict,
) -> dict:
    """Patchable boundary for agent invocation in tests."""
    return {
        "role_id": role_id,
        "confidence": 0.8,
        "cost_usd": 0.05,
        "output": {
            "headline": "Event Deep-Dive Memo",
            "executive_summary": "stub executive summary",
            "event_analysis": {},
            "market_impact": {},
            "per_company_recommendations": [],
            "historical_analogies": [],
            "risk_flags": [],
            "confidence": 0.8,
        },
    }


async def narrative_writer(
    state: DeepDiveWorkflowState,
    *,
    registry: Any,
    cost_accumulator: CostAccumulator,
    langfuse_client: Any = None,
) -> DeepDiveWorkflowState:
    """Invoke the narrative-writer agent to produce the final MemoDraft.

    This is the LAST AgentNode.  Always sets state.memo_draft.

    Inputs: all prior agent outputs.
    Outputs: state.memo_draft (MemoDraft), state.confidence_scores[_ROLE_ID].

    Raises:
        CostCeilingExceededError: If cost would exceed ceiling.
    """
    definition = registry.resolve(_ROLE_ID)

    input_payload = {
        "event_full": (
            state.event_full.model_dump(mode="json")
            if state.event_full is not None
            else None
        ),
        "event_analysis": state.exposure_output,
        "historical_context": state.historical_output,
        "recommendation": state.recommendation,
        "exposure_analyses": [
            a.model_dump(mode="json") for a in state.exposure_analyses
        ],
        "market_reaction": {
            k: v.model_dump(mode="json")
            for k, v in state.market_reaction.items()
        },
    }

    result = await _invoke_agent(_ROLE_ID, definition, input_payload)

    cost_accumulator.add(result["cost_usd"])

    # Build MemoDraft from agent output
    output = result.get("output") or {}
    memo = MemoDraft(
        headline=output.get("headline", ""),
        executive_summary=output.get("executive_summary", ""),
        event_analysis=output.get("event_analysis", {}),
        market_impact=output.get("market_impact", {}),
        per_company_recommendations=output.get("per_company_recommendations", []),
        historical_analogies=output.get("historical_analogies", []),
        risk_flags=output.get("risk_flags", []),
        confidence=result["confidence"],
    )

    new_scores = {**state.confidence_scores, _ROLE_ID: result["confidence"]}
    new_state = state.model_copy(
        update={
            "memo_draft": memo,
            "report": output,  # also write to base WorkflowState.report
            "confidence_scores": new_scores,
            "cost_usd": state.cost_usd + result["cost_usd"],
        }
    )

    logger.info(
        "narrative_writer: memo_draft set, confidence=%.2f cost_usd=%.4f",
        result["confidence"],
        result["cost_usd"],
    )
    return new_state
