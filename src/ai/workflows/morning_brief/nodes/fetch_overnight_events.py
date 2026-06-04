"""
src.ai.workflows.morning_brief.nodes.fetch_overnight_events — DeterministicNode.

Queries the event repository for events in the last 24 hours. Handles
InsufficientData gracefully: returns empty events list so the workflow
continues without sending a brief (no events = nothing to brief on).

No LLM calls. Tool call returns bounded Pydantic results (<=50 rows per §7.3).

PLAN-F-006 TASK-003
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.morning_brief_state import MorningBriefState

logger = logging.getLogger(__name__)


class InsufficientData(Exception):
    """Raised by the event repository when there are insufficient events to process."""

    def __init__(self, reason: str = "insufficient data") -> None:
        super().__init__(reason)
        self.reason = reason


async def fetch_overnight_events(
    state: MorningBriefState,
    *,
    event_repo: Any,
    lookback_hours: int = 24,
) -> MorningBriefState:
    """Query the event repository for events in the last N hours.

    Handles InsufficientData gracefully by returning empty events list,
    allowing the workflow to continue and exit cleanly without sending a brief.

    Args:
        state: Current MorningBriefState.
        event_repo: Repository with get_events_in_window(tenant_id, hours).
        lookback_hours: How many hours back to query (default 24).

    Returns:
        Updated state with events list populated (may be empty).
    """
    try:
        events = await event_repo.get_events_in_window(
            tenant_id=state.tenant_id,
            hours=lookback_hours,
        )
    except InsufficientData as exc:
        logger.info(
            "fetch_overnight_events: insufficient data for tenant=%s — %s; "
            "proceeding with empty events",
            state.tenant_id,
            exc.reason,
        )
        events = []

    events = events or []

    logger.debug(
        "fetch_overnight_events: fetched %d events for tenant=%s (last %dh)",
        len(events),
        state.tenant_id,
        lookback_hours,
    )

    return state.model_copy(update={"events": events})
