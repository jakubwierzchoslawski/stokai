"""
ai.workflows.on_demand.nodes.fetch_active_events — DeterministicNode.

Queries geo_event JOIN event_exposure for events in the last 30 days where
company_id matches; caps at 50 rows. Empty result is valid.
"""
from __future__ import annotations

from src.ai.workflows.state import WorkflowState

_LOOKBACK_DAYS = 30
_MAX_EVENTS = 50


async def fetch_active_events(
    state: WorkflowState,
    *,
    geo_event_repo: object,
) -> WorkflowState:
    """Load active geo-events for the company and populate state.active_events.

    Args:
        state: Current workflow state (immutable input).
        geo_event_repo: Repository implementing IGeoEventRepository protocol.

    Returns:
        New WorkflowState with active_events populated (may be empty list).
    """
    events = await geo_event_repo.get_active_events_for_company(
        state.company_id,
        state.tenant_id,
        _LOOKBACK_DAYS,
        _MAX_EVENTS,
    )

    return state.model_copy(update={"active_events": list(events)})
