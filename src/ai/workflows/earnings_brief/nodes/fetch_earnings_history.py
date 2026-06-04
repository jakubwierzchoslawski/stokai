"""
ai.workflows.earnings_brief.nodes.fetch_earnings_history — DeterministicNode.

Queries past 8 earnings events for the company.

PLAN-F-009 TASK-004
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.earnings_brief.state import EarningsBriefState

logger = logging.getLogger(__name__)

_MAX_HISTORY_RECORDS = 8


async def fetch_earnings_history(
    state: EarningsBriefState,
    ctx: Any,  # NodeContext
) -> EarningsBriefState:
    """DeterministicNode: fetch past earnings history for the company.

    Queries earnings_event for the company's past 8 earnings events
    (chronological descending), including reported_eps, estimated_eps,
    and surprise_pct. Returns empty list when no history exists (not an error).

    Args:
        state: Current EarningsBriefState.
        ctx: NodeContext with injected repositories.

    Returns:
        Updated EarningsBriefState with earnings_history populated.
    """
    logger.debug(
        "fetch_earnings_history: company_id=%s tenant_id=%s",
        state.company_id,
        state.tenant_id,
    )

    history: list[dict[str, Any]] = []

    if ctx.earnings_repo is not None:
        records = await ctx.earnings_repo.list_history(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
            limit=_MAX_HISTORY_RECORDS,
        )
        history = [
            r.model_dump() if hasattr(r, "model_dump") else dict(r)
            for r in (records or [])
        ]
    # Empty list when no history — not an error

    return state.model_copy(update={"earnings_history": history})
