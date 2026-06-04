"""
ai.workflows.earnings_brief.nodes.fetch_macro_context — DeterministicNode.

Queries FRED macro indicators via the cache-or-fetch layer.

PLAN-F-009 TASK-004
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.earnings_brief.state import EarningsBriefState

logger = logging.getLogger(__name__)

_MAX_INDICATORS = 10


async def fetch_macro_context(
    state: EarningsBriefState,
    ctx: Any,  # NodeContext
) -> EarningsBriefState:
    """DeterministicNode: fetch FRED macro indicators snapshot.

    Queries CPI, Fed Funds Rate, 10Y Treasury Yield, GDP growth via the
    cache-or-fetch layer. Caps at 10 indicators (bounded output).

    Args:
        state: Current EarningsBriefState.
        ctx: NodeContext with injected repositories.

    Returns:
        Updated EarningsBriefState with macro_context populated.
    """
    logger.debug(
        "fetch_macro_context: tenant_id=%s",
        state.tenant_id,
    )

    indicators: list[dict[str, Any]] = []

    if ctx.macro_repo is not None:
        raw = await ctx.macro_repo.get_latest_indicators(
            tenant_id=state.tenant_id,
        )
        indicators = [
            r.model_dump() if hasattr(r, "model_dump") else dict(r)
            for r in (raw or [])
        ]
        # Cap at _MAX_INDICATORS
        indicators = indicators[:_MAX_INDICATORS]

    macro_context: dict[str, Any] = {
        "indicators": indicators,
        "indicator_count": len(indicators),
    }

    return state.model_copy(update={"macro_context": macro_context})
