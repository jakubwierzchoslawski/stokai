"""
src.ai.workflows.morning_brief.nodes.block_and_log — Terminal DeterministicNode.

Invoked when confidence < 0.40. Records the blocked run in the audit trail
(brief table + workflow_run + episodic memory). No email is dispatched.

Satisfies AC-004: admin AI audit console records the blocked run.

PLAN-F-006 TASK-008
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.ai.schemas.morning_brief_state import HilStatus
from src.ai.workflows.morning_brief_state import ConfidenceRoute, MorningBriefState

logger = logging.getLogger(__name__)


async def block_and_log(
    state: MorningBriefState,
    *,
    brief_repo: Any | None = None,
    workflow_repo: Any | None = None,
    episodic_repo: Any | None = None,
) -> MorningBriefState:
    """Block the brief and persist the blocked run to the audit trail.

    Steps:
    1. Creates BriefRow with hil_status=NOT_REQUIRED and sent_at=None.
    2. Persists the BriefRow to brief table (if brief_repo provided).
    3. Writes workflow_run row with status="blocked" (if workflow_repo provided).
    4. Writes Layer 1 episodic memory entry (if episodic_repo provided).
    5. Does NOT dispatch any email.

    Args:
        state: Current MorningBriefState.
        brief_repo: Optional repository with insert(dto) method.
        workflow_repo: Optional repository with update_status() method.
        episodic_repo: Optional episodic memory repository with write() method.

    Returns:
        Updated state with confidence_route=BLOCK.
    """
    from src.storage.repositories.morning_brief_repository import MorningBriefCreate

    confidence = (
        min(state.confidence_scores.values()) if state.confidence_scores else 0.0
    )

    logger.warning(
        "block_and_log: Morning Brief blocked for workflow_id=%s tenant_id=%s "
        "overall_confidence=%.3f (threshold=0.40) — no email dispatched",
        state.workflow_id,
        state.tenant_id,
        confidence,
    )

    # 1. Persist brief row
    if brief_repo is not None:
        create_dto = MorningBriefCreate(
            brief_id=state.brief_id or uuid4(),
            brief_type="morning_brief",
            user_id=state.user_id,
            tenant_id=state.tenant_id,
            workflow_id=state.workflow_id,
            content=state.report or "",
            confidence=confidence,
            cost_usd=state.cost_usd,
        )
        # Pass hil_status as kwarg for the brief_repo.insert call
        create_dto_dict = create_dto.model_dump()
        create_dto_dict["hil_status"] = HilStatus.NOT_REQUIRED
        # Use a simple create_dto object with hil_status attribute
        class _CreateWithHilStatus:
            def __init__(self, dto_dict: dict) -> None:
                self.__dict__.update(dto_dict)
        enriched_dto = _CreateWithHilStatus(create_dto_dict)
        await brief_repo.insert(enriched_dto)

    # 2. Write workflow_run blocked status
    if workflow_repo is not None:
        await workflow_repo.update_status(
            workflow_id=state.workflow_id,
            tenant_id=state.tenant_id,
            status="blocked",
        )

    # 3. Write Layer 1 episodic memory entry
    if episodic_repo is not None:
        await episodic_repo.write({
            "workflow_id": str(state.workflow_id),
            "workflow_type": state.workflow_type,
            "user_id": str(state.user_id),
            "tenant_id": str(state.tenant_id),
            "status": "blocked",
            "confidence": confidence,
            "blocked_at": datetime.now(tz=timezone.utc).isoformat(),
        })

    return state.model_copy(
        update={
            "confidence_route": ConfidenceRoute.BLOCK,
        }
    )
