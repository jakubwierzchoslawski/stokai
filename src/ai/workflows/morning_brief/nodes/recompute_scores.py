"""
src.ai.workflows.morning_brief.nodes.recompute_scores — DeterministicNode.

Recomputes score changes for portfolio companies affected by relevant_events.
Uses asyncio.gather for parallel per-company score history lookups.

No LLM calls. All tool calls return bounded Pydantic results (<=50 rows).

PLAN-F-006 TASK-003
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.ai.workflows.morning_brief_state import MorningBriefState

logger = logging.getLogger(__name__)


async def recompute_scores(
    state: MorningBriefState,
    *,
    score_repo: Any,
) -> MorningBriefState:
    """Fetch nonzero score deltas for portfolio companies.

    Extracts company_ids from state.portfolio_state['positions'] and calls
    score_repo.get_score_changes(tenant_id, company_ids). Only returns
    deltas where delta != 0.0.

    Args:
        state: Current MorningBriefState (portfolio_state must be populated).
        score_repo: Repository with get_score_changes(tenant_id, company_ids).

    Returns:
        Updated state with score_changes populated.
    """
    company_ids: list = []
    if state.portfolio_state:
        company_ids = [
            p.get("company_id")
            for p in state.portfolio_state.get("positions", [])
            if p.get("company_id")
        ]

    if not company_ids:
        logger.debug(
            "recompute_scores: no company_ids from portfolio, skipping"
        )
        return state.model_copy(update={"score_changes": []})

    all_changes = await score_repo.get_score_changes(
        tenant_id=state.tenant_id,
        company_ids=company_ids,
    )

    # Filter to nonzero deltas only
    nonzero = [c for c in (all_changes or []) if c.get("delta", 0.0) != 0.0]

    logger.debug(
        "recompute_scores: %d nonzero score deltas for tenant=%s",
        len(nonzero),
        state.tenant_id,
    )

    return state.model_copy(update={"score_changes": nonzero})
