"""
src.ai.workflows.morning_brief.nodes.hil_queue_node — DeterministicNode.

Invoked when confidence is in [0.40, 0.70). Persists the brief with
hil_status=PENDING and enqueues it in the HIL review queue with a 05:45
deadline. Checkpoints LangGraph state to PostgreSQL (graph pauses here).
Does NOT dispatch email.

PLAN-F-006 TASK-011
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState

logger = logging.getLogger(__name__)

_HIL_HOUR = 5
_HIL_MINUTE = 45


def _compute_hil_deadline(now: datetime) -> datetime:
    """Return the next 05:45 UTC deadline.

    If 05:45 today is still in the future, returns today's occurrence.
    Otherwise returns tomorrow's.
    """
    candidate = now.replace(
        hour=_HIL_HOUR, minute=_HIL_MINUTE, second=0, microsecond=0
    )
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate


async def hil_queue_node(
    state: MorningBriefState,
    *,
    hil_repo: Any,
    brief_repo: Any | None = None,
    now: datetime | None = None,
) -> MorningBriefState:
    """Enqueue the brief for human-in-the-loop review (deadline 05:45 UTC).

    1. Persists a BriefRow with hil_status=PENDING (if brief_repo provided).
    2. Calls HILQueueRepository.enqueue with review_deadline and checkpoint_id.
    3. Returns without dispatching email.

    Args:
        state: Current MorningBriefState.
        hil_repo: HILQueueRepository with create(HILQueueItemCreate) method.
        brief_repo: Optional MorningBriefRepository for inserting the brief row.
        now: Current UTC datetime (injected for testability).

    Returns:
        Updated state with requires_hil=True and confidence_route=HIL.
    """
    from src.storage.repositories.hil_queue_repository import (
        HILQueueItemCreate,
        HILStatus,
    )

    _now = now or datetime.now(tz=timezone.utc)
    review_deadline = _compute_hil_deadline(_now)

    confidence = (
        min(state.confidence_scores.values()) if state.confidence_scores else 0.0
    )

    # Persist brief row with PENDING status
    if brief_repo is not None:
        from src.storage.repositories.morning_brief_repository import MorningBriefCreate
        create_dto = MorningBriefCreate(
            user_id=state.user_id,
            tenant_id=state.tenant_id,
            workflow_id=state.workflow_id,
            content=state.report or "",
            confidence=confidence,
            cost_usd=state.cost_usd,
        )
        brief = await brief_repo.insert(create_dto)
        await brief_repo.update_hil_status(brief.brief_id, state.tenant_id, "pending")

    # Create HIL queue item
    checkpoint_id = f"hil:{state.workflow_id}"
    dto = HILQueueItemCreate(
        workflow_run_id=state.workflow_id,
        workflow_type="morning_brief",
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        confidence=confidence,
        scheduled_send_at=review_deadline,
        lc_checkpoint_id=checkpoint_id,
    )

    queue_item = await hil_repo.create(dto)

    logger.info(
        "hil_queue_node: enqueued morning brief for workflow_id=%s "
        "deadline=%s item_id=%s",
        state.workflow_id,
        review_deadline.isoformat(),
        queue_item.item_id,
    )

    return state.model_copy(
        update={
            "requires_hil": True,
            "hil_reason": "Confidence below auto-send threshold (0.70)",
            "confidence_route": ConfidenceRoute.HIL,
        }
    )
