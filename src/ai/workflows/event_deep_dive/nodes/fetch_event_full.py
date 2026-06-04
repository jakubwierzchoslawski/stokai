"""
ai.workflows.event_deep_dive.nodes.fetch_event_full — DeterministicNode.

Reads event_id from state.inputs["event_id"], fetches the GeoEvent row and
its associated exposure rows, then writes state.event_full.

PLAN-F-010 TASK-004.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from src.ai.workflows.event_deep_dive.exceptions import WorkflowInputError
from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState, GeoEvent

logger = logging.getLogger(__name__)


async def fetch_event_full(
    state: DeepDiveWorkflowState,
    *,
    geo_event_repo: Any,
    event_exposure_repo: Any,
) -> DeepDiveWorkflowState:
    """Fetch the full GeoEvent record and its exposure rows.

    Reads event_id from state.inputs["event_id"].
    Writes:
      - state.event_full (GeoEvent instance)

    Args:
        state: Current DeepDiveWorkflowState.
        geo_event_repo: IGeoEventRepository implementation.
        event_exposure_repo: IEventExposureRepository-compatible object with
            a list_by_event_id(event_id) method.

    Returns:
        Updated state with event_full populated.

    Raises:
        WorkflowInputError: If event_id is missing from inputs or the event
            does not exist in the database.
    """
    raw_event_id = state.inputs.get("event_id")
    if not raw_event_id:
        raise WorkflowInputError(
            "Missing required input: 'event_id' not found in state.inputs"
        )

    try:
        event_id = UUID(str(raw_event_id))
    except (ValueError, AttributeError) as exc:
        raise WorkflowInputError(
            f"Invalid event_id format: {raw_event_id!r}"
        ) from exc

    logger.debug("fetch_event_full: looking up event_id=%s", event_id)

    row = await geo_event_repo.get_by_id(event_id)
    if row is None:
        raise WorkflowInputError(
            f"Event not found: event_id={event_id} "
            f"(workflow_id={state.workflow_id})"
        )

    # Build GeoEvent from the repository row
    # GeoEventRow stores attrs as plain attributes — handle both dict and obj
    def _attr(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    # Fetch exposure rows
    exposures: list[dict] = []
    if hasattr(event_exposure_repo, "list_by_event_id"):
        raw_exposures = await event_exposure_repo.list_by_event_id(event_id)
        exposures = [
            e if isinstance(e, dict) else e.__dict__
            for e in raw_exposures
        ]

    geo_event = GeoEvent(
        event_id=event_id,
        tenant_id=_attr(row, "tenant_id"),
        title=_attr(row, "title"),
        summary=_attr(row, "summary"),
        source_provider=_attr(row, "source_provider"),
        category=_attr(row, "category") or [],
        intensity=_attr(row, "intensity"),
        sentiment=_attr(row, "sentiment"),
        geo_regions=_attr(row, "geo_regions") or [],
        affected_sectors=_attr(row, "affected_sectors") or [],
        cameo_code=_attr(row, "cameo_code"),
        lat=_attr(row, "lat"),
        lon=_attr(row, "lon"),
        occurred_at=_attr(row, "occurred_at"),
        exposures=exposures,
    )

    new_state = state.model_copy(update={"event_full": geo_event})
    logger.info(
        "fetch_event_full: loaded event_id=%s title=%r exposures=%d",
        event_id,
        geo_event.title,
        len(exposures),
    )
    return new_state
