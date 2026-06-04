"""
src.ai.workflows.morning_brief.nodes.fetch_portfolio — DeterministicNode.

Loads the user's portfolio snapshot via the portfolio repository. Raises
WorkflowAbortError if the portfolio is empty (nothing to brief on).

No LLM calls. Tool call returns bounded Pydantic results (<=50 rows per §7.3).

PLAN-F-006 TASK-003
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.morning_brief_state import MorningBriefState

logger = logging.getLogger(__name__)


class WorkflowAbortError(Exception):
    """Raised when a workflow cannot proceed due to missing prerequisite data.

    Distinct from WorkflowCostCeilingExceeded — abort means "no data to work
    with" rather than a cost/time overrun.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def fetch_portfolio(
    state: MorningBriefState,
    *,
    portfolio_repo: Any,
    user_id: Any = None,
    tenant_id: Any = None,
) -> MorningBriefState:
    """Load positions and watchlist for the workflow user.

    Calls portfolio_repo.get_positions(user_id, tenant_id) and
    portfolio_repo.get_watchlist(user_id, tenant_id).

    Args:
        state: Current MorningBriefState.
        portfolio_repo: Repository with get_positions() and get_watchlist().
        user_id: Override user_id (defaults to state.user_id).
        tenant_id: Override tenant_id (defaults to state.tenant_id).

    Returns:
        Updated state with portfolio_state populated.

    Raises:
        WorkflowAbortError: When both positions and watchlist are empty.
    """
    _user_id = user_id or state.user_id
    _tenant_id = tenant_id or state.tenant_id

    positions = await portfolio_repo.get_positions(_user_id, _tenant_id)
    watchlist = await portfolio_repo.get_watchlist(_user_id, _tenant_id)

    positions = positions or []
    watchlist = watchlist or []

    if not positions and not watchlist:
        logger.warning(
            "fetch_portfolio: empty portfolio for user=%s tenant=%s — aborting workflow",
            _user_id,
            _tenant_id,
        )
        raise WorkflowAbortError(
            f"Portfolio is empty for user={_user_id}; no brief to generate."
        )

    portfolio_state = {
        "positions": positions,
        "watchlist": watchlist,
    }

    logger.debug(
        "fetch_portfolio: loaded %d positions, %d watchlist items for user=%s",
        len(positions),
        len(watchlist),
        _user_id,
    )

    return state.model_copy(update={"portfolio_state": portfolio_state})
