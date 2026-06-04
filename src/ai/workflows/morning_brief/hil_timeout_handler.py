"""
src.ai.workflows.morning_brief.hil_timeout_handler — HIL 05:45 timeout handler.

Celery beat task scheduled at 05:45 UTC that sweeps the brief table for PENDING
morning_brief rows:

- Unreviewed (PENDING past deadline): sets hil_status=TIMED_OUT, sends
  "No Morning Brief today" email, writes Layer 4 user_feedback entry.
- Approved (APPROVED by reviewer): resumes LangGraph graph from checkpoint,
  runs narrative_writer_node -> format_and_dispatch.

Uses SELECT...FOR UPDATE SKIP LOCKED to prevent race conditions.

PLAN-F-006 TASK-011
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


async def handle_hil_timeouts(
    *,
    brief_repo: Any,
    hil_repo: Any,
    email_dispatcher: Any,
    user_feedback_repo: Any,
    graph_runner: Any | None = None,
    now: datetime | None = None,
) -> dict:
    """Process all PENDING morning brief HIL items at/after the 05:45 deadline.

    For unreviewed items (status=PENDING and deadline passed):
    - Sets hil_status=TIMED_OUT on the brief row.
    - Sends "No Morning Brief today" notification email.
    - Writes a Layer 4 user_feedback entry.

    For approved items (status=APPROVED by reviewer):
    - Resumes the LangGraph graph from checkpoint.
    - Runs narrative_writer_node -> format_and_dispatch.

    Args:
        brief_repo: MorningBriefRepository.
        hil_repo: HILQueueRepository with list_timed_out_pending(now) and
                  update_status() methods.
        email_dispatcher: Email dispatcher with send_no_brief_notification().
        user_feedback_repo: Repository with write(entry) method.
        graph_runner: Optional graph runner with resume(checkpoint_id) method.
        now: Current UTC datetime (injected for testability).

    Returns:
        dict with counts: timed_out, resumed.
    """
    _now = now or datetime.now(tz=timezone.utc)
    timed_out_count = 0
    resumed_count = 0

    try:
        pending_items = await hil_repo.list_timed_out_pending(_now)
    except Exception as exc:
        logger.error(
            "hil_timeout_handler: failed to query pending items — %s", exc
        )
        return {"timed_out": 0, "resumed": 0}

    for item in pending_items:
        try:
            await _process_hil_item(
                item=item,
                hil_repo=hil_repo,
                brief_repo=brief_repo,
                email_dispatcher=email_dispatcher,
                user_feedback_repo=user_feedback_repo,
                graph_runner=graph_runner,
                now=_now,
            )
            timed_out_count += 1
        except Exception as exc:
            logger.error(
                "hil_timeout_handler: error processing item_id=%s — %s",
                getattr(item, "item_id", "unknown"),
                exc,
            )

    # Process approved items if graph_runner is available
    if graph_runner is not None:
        try:
            approved_items = await hil_repo.list_approved_pending_dispatch(_now)
            for item in approved_items:
                try:
                    await _resume_approved(item, graph_runner, hil_repo)
                    resumed_count += 1
                except Exception as exc:
                    logger.error(
                        "hil_timeout_handler: failed to resume approved item_id=%s — %s",
                        getattr(item, "item_id", "unknown"),
                        exc,
                    )
        except AttributeError:
            # list_approved_pending_dispatch may not be implemented yet
            pass

    logger.info(
        "hil_timeout_handler: processed %d timed-out, %d resumed",
        timed_out_count,
        resumed_count,
    )

    return {"timed_out": timed_out_count, "resumed": resumed_count}


async def _process_hil_item(
    *,
    item: Any,
    hil_repo: Any,
    brief_repo: Any,
    email_dispatcher: Any,
    user_feedback_repo: Any,
    graph_runner: Any | None,
    now: datetime,
) -> None:
    """Process a single timed-out PENDING HIL item."""
    from src.storage.repositories.hil_queue_repository import HILStatus

    item_id = item.item_id
    tenant_id = item.tenant_id
    user_id = item.user_id
    workflow_run_id = item.workflow_run_id

    logger.info(
        "hil_timeout_handler: timing out item_id=%s workflow_id=%s user_id=%s",
        item_id,
        workflow_run_id,
        user_id,
    )

    # Update HIL queue item to TIMED_OUT
    await hil_repo.update_status(
        item_id=item_id,
        tenant_id=tenant_id,
        status=HILStatus.TIMED_OUT,
    )

    # Update brief row hil_status to timed_out
    try:
        brief = await brief_repo.get_latest_by_user(user_id, tenant_id)
        if brief is not None:
            await brief_repo.update_hil_status(brief.brief_id, tenant_id, "timed_out")
    except Exception as exc:
        logger.warning(
            "hil_timeout_handler: could not update brief hil_status — %s", exc
        )

    # Send "No Morning Brief today" notification
    try:
        await email_dispatcher.send_no_brief_notification(
            user_id=user_id,
            tenant_id=tenant_id,
            reason="The morning brief was pending review and was not approved by 05:45.",
        )
    except Exception as exc:
        logger.warning(
            "hil_timeout_handler: failed to send timeout notification to user=%s — %s",
            user_id,
            exc,
        )

    # Write Layer 4 user_feedback entry
    try:
        await user_feedback_repo.write({
            "workflow_run_id": str(workflow_run_id),
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "feedback_type": "hil_timeout",
            "status": "timed_out",
            "occurred_at": now.isoformat(),
        })
    except Exception as exc:
        logger.warning(
            "hil_timeout_handler: could not write feedback entry for item_id=%s — %s",
            item_id,
            exc,
        )


async def _resume_approved(
    item: Any,
    graph_runner: Any,
    hil_repo: Any,
) -> None:
    """Resume the LangGraph graph for an approved HIL item."""
    from src.storage.repositories.hil_queue_repository import HILStatus

    checkpoint_id = item.lc_checkpoint_id
    logger.info(
        "hil_timeout_handler: resuming approved item_id=%s checkpoint=%s",
        item.item_id,
        checkpoint_id,
    )

    await graph_runner.resume(checkpoint_id)

    await hil_repo.update_status(
        item_id=item.item_id,
        tenant_id=item.tenant_id,
        status=HILStatus.APPROVED,
    )
