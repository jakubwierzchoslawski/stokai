"""
ai.workflows.earnings_brief.nodes.fetch_sector_recent_earnings — DeterministicNode.

Queries sector peers' recent earnings results.

PLAN-F-009 TASK-004
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.earnings_brief.state import EarningsBriefState

logger = logging.getLogger(__name__)

_MAX_SECTOR_PEERS = 20
_SECTOR_LOOKBACK_DAYS = 90


async def fetch_sector_recent_earnings(
    state: EarningsBriefState,
    ctx: Any,  # NodeContext
) -> EarningsBriefState:
    """DeterministicNode: fetch recent earnings results from sector peers.

    Queries earnings_event joined with company to retrieve earnings results
    from sector peers in the last 90 days. Returns at most 20 rows (bounded).

    Args:
        state: Current EarningsBriefState.
        ctx: NodeContext with injected repositories.

    Returns:
        Updated EarningsBriefState with sector_recent_earnings populated.
    """
    logger.debug(
        "fetch_sector_recent_earnings: company_id=%s tenant_id=%s",
        state.company_id,
        state.tenant_id,
    )

    peer_earnings: list[dict[str, Any]] = []

    if ctx.earnings_repo is not None:
        raw = await ctx.earnings_repo.list_sector_recent(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
            lookback_days=_SECTOR_LOOKBACK_DAYS,
            limit=_MAX_SECTOR_PEERS,
        )
        peer_earnings = [
            r.model_dump() if hasattr(r, "model_dump") else dict(r)
            for r in (raw or [])
        ]
        # Cap at _MAX_SECTOR_PEERS
        peer_earnings = peer_earnings[:_MAX_SECTOR_PEERS]

    return state.model_copy(update={"sector_recent_earnings": peer_earnings})
