"""
src.ai.workflows.morning_brief.nodes.format_and_dispatch — DeterministicNode.

Runs after narrative_writer_node on the auto-send or HIL-approved path.
Reads state.report (HTML), reads user dispatch_time, and calls the SendGrid
dispatcher. On success: updates BriefRow.sent_at. On error: logs and sets
workflow_run.status="dispatch_failed" without raising.

PLAN-F-006 TASK-010
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.ai.workflows.morning_brief_state import MorningBriefState

logger = logging.getLogger(__name__)

_DEFAULT_DISPATCH_TIME = "06:00"


async def format_and_dispatch(
    state: MorningBriefState,
    *,
    dispatcher: Any,
    brief_repo: Any,
    workflow_repo: Any,
    user_repo: Any,
    user_email: str,
) -> MorningBriefState:
    """Format and dispatch the morning brief via SendGrid.

    1. Reads state.report (HTML).
    2. Reads user.dispatch_time from user_repo (defaults to 06:00 if None).
    3. Calls dispatcher.send_morning_brief(..., scheduled_for=dispatch_time).
    4. On success: updates BriefRow.sent_at = now().
    5. On SendGrid error: logs, sets workflow_run.status="dispatch_failed",
       does NOT raise (brief persisted; retry can be triggered manually).

    Args:
        state: Current MorningBriefState (report and brief_id must be set).
        dispatcher: Email dispatcher with send_morning_brief() method.
        brief_repo: Repository with update_sent_at() method.
        workflow_repo: Repository with update_status() method.
        user_repo: Repository with get_dispatch_time(user_id, tenant_id) method.
        user_email: Recipient email address.

    Returns:
        Updated state (unchanged on error, brief_id preserved).
    """
    html_body = state.report or ""

    # Read user dispatch_time (per-user configurable, D7)
    try:
        dispatch_time = await user_repo.get_dispatch_time(
            state.user_id, state.tenant_id
        )
    except Exception as exc:
        logger.warning(
            "format_and_dispatch: failed to read user dispatch_time — %s; "
            "defaulting to %s",
            exc,
            _DEFAULT_DISPATCH_TIME,
        )
        dispatch_time = None

    scheduled_for = dispatch_time or _DEFAULT_DISPATCH_TIME

    try:
        await dispatcher.send_morning_brief(
            to=user_email,
            subject="StokAI Morning Brief",
            html_body=html_body,
            brief_id=state.brief_id,
            scheduled_for=scheduled_for,
        )
        logger.info(
            "format_and_dispatch: dispatched brief_id=%s to %s scheduled_for=%s",
            state.brief_id,
            user_email,
            scheduled_for,
        )

        # Update sent_at on success
        if state.brief_id is not None:
            await brief_repo.update_sent_at(
                brief_id=state.brief_id,
                tenant_id=state.tenant_id,
                sent_at=datetime.now(tz=timezone.utc),
            )

    except Exception as exc:
        logger.error(
            "format_and_dispatch: SendGrid error for brief_id=%s workflow_id=%s — %s",
            state.brief_id,
            state.workflow_id,
            type(exc).__name__,
        )
        # Do not re-raise; set dispatch_failed status on workflow_run
        try:
            await workflow_repo.update_status(
                workflow_id=state.workflow_id,
                tenant_id=state.tenant_id,
                status="dispatch_failed",
            )
        except Exception as repo_exc:
            logger.warning(
                "format_and_dispatch: also failed to set dispatch_failed status — %s",
                repo_exc,
            )

    return state
