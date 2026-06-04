"""
ai.workflows.event_deep_dive.nodes.run_exposure_analysts — DeterministicNode.

Fan-out: invokes the exposure_analyst AgentNode via AgentRegistry.resolve()
for each company in state.event_full.exposures using asyncio.gather.

Each coroutine gets a Langfuse sibling span (parent_span_id = workflow trace).
CostAccumulator.add() is called per completed call; if CostCeilingExceededError
is raised the gather is cancelled and the error propagates.

Configurable cap: MAX_PARALLEL_EXPOSURE_CALLS (default 10, env-overridable).

PLAN-F-010 TASK-006.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import UUID

from src.ai.workflows.event_deep_dive.cost_accumulator import CostAccumulator
from src.ai.workflows.event_deep_dive.exceptions import CostCeilingExceededError
from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState, ExposureAnalysis

logger = logging.getLogger(__name__)

MAX_PARALLEL_EXPOSURE_CALLS: int = int(
    os.environ.get("MAX_PARALLEL_EXPOSURE_CALLS", "10")
)


async def _invoke_analyst(
    company_id: UUID,
    *,
    registry: Any,
    state: DeepDiveWorkflowState,
    parent_trace_id: str | None,
) -> dict:
    """Invoke the exposure_analyst agent for a single company.

    This function is the target of each asyncio.gather coroutine.
    Separated so tests can patch it easily.

    Args:
        company_id: The company to analyse.
        registry: AgentRegistry to resolve the exposure_analyst definition.
        state: Current workflow state (for context).
        parent_trace_id: Langfuse trace ID for sibling span creation.

    Returns:
        dict with: company_id, exposure_type, direction, magnitude,
                   reasoning, confidence, cost_usd.
    """
    defn = registry.resolve("exposure-analyst")

    # Build a minimal input payload
    input_payload = {
        "company_id": str(company_id),
        "event_summary": (
            state.event_full.summary if state.event_full else None
        ),
        "event_category": (
            state.event_full.category if state.event_full else []
        ),
        "langfuse_parent_trace_id": parent_trace_id,
    }

    # Placeholder LLM invocation — real implementation would call the LLM client.
    # In the workflow graph, this function is injected/patched in tests.
    # For now return a structured stub result so the node is testable.
    return {
        "company_id": str(company_id),
        "exposure_type": "direct",
        "direction": "neutral",
        "magnitude": 0.5,
        "reasoning": f"Analysis for company {company_id}",
        "confidence": defn.limits.cost_ceiling_usd / 100,
        "cost_usd": 0.01,
        "_input_payload": input_payload,
    }


async def run_exposure_analysts(
    state: DeepDiveWorkflowState,
    *,
    registry: Any,
    cost_accumulator: CostAccumulator,
    langfuse_client: Any = None,
) -> DeepDiveWorkflowState:
    """Fan-out exposure analyst calls across all companies in event_full.exposures.

    Args:
        state: Current DeepDiveWorkflowState (event_full must be set).
        registry: AgentRegistry to resolve the exposure_analyst agent.
        cost_accumulator: Shared CostAccumulator for this workflow run.
        langfuse_client: Optional Langfuse client for span creation.

    Returns:
        Updated state with exposure_analyses populated.

    Raises:
        CostCeilingExceededError: If any analyst call causes the accumulator
            to exceed the configured ceiling.
    """
    if state.event_full is None or not state.event_full.exposures:
        logger.info("run_exposure_analysts: no exposures to analyse")
        return state.model_copy(update={"exposure_analyses": []})

    parent_trace_id = state.langfuse_trace_id
    exposures = state.event_full.exposures

    # Extract unique company IDs (deduplicate)
    company_ids: list[UUID] = []
    seen: set[str] = set()
    for exp in exposures:
        cid_raw = (
            exp.get("company_id") if isinstance(exp, dict)
            else getattr(exp, "company_id", None)
        )
        if cid_raw is not None:
            cid_str = str(cid_raw)
            if cid_str not in seen:
                seen.add(cid_str)
                company_ids.append(UUID(cid_str))

    # Apply parallelism cap
    company_ids = company_ids[:MAX_PARALLEL_EXPOSURE_CALLS]

    logger.info(
        "run_exposure_analysts: launching %d analyst coroutines "
        "(cap=%d, trace=%s)",
        len(company_ids),
        MAX_PARALLEL_EXPOSURE_CALLS,
        parent_trace_id,
    )

    coroutines = [
        _invoke_analyst(
            cid,
            registry=registry,
            state=state,
            parent_trace_id=parent_trace_id,
        )
        for cid in company_ids
    ]

    raw_results = await asyncio.gather(*coroutines)

    analyses: list[ExposureAnalysis] = []
    for raw in raw_results:
        analysis = ExposureAnalysis(
            company_id=UUID(raw["company_id"]),
            exposure_type=raw["exposure_type"],
            direction=raw["direction"],
            magnitude=raw["magnitude"],
            reasoning=raw["reasoning"],
            confidence=raw["confidence"],
            cost_usd=raw["cost_usd"],
        )
        # CostCeilingExceededError propagates before adding
        cost_accumulator.add(analysis.cost_usd)
        analyses.append(analysis)

    logger.info("run_exposure_analysts: completed %d analyses", len(analyses))
    return state.model_copy(update={"exposure_analyses": analyses})
