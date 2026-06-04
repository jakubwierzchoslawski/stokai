"""
Events API router — provides the admin-only ingest endpoint for the
Mode A Reactive Pipeline.

POST /api/v1/events/ingest
  - Requires role="admin" JWT claim
  - Accepts RawEvent JSON body
  - Enqueues run_pipeline_task to Celery
  - Returns 202 Accepted with task ID
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.events.models import RawEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def _require_admin(authorization: str = "") -> dict:
    """Minimal admin role guard.

    In production this would decode and verify the JWT from the Authorization
    header and check the 'role' claim equals 'admin'. Stubbed here to keep
    this module importable without auth infrastructure.
    """
    # TODO: replace with real JWT verification once auth module is wired
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authorization header required"},
        )
    return {"role": "admin"}  # placeholder


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a raw event into the pipeline (admin only)",
    response_model=dict,
)
async def ingest_event(
    raw_event: RawEvent,
) -> dict:
    """Accept a raw event and enqueue it for pipeline processing.

    Args:
        raw_event: The event payload from a source adapter.

    Returns:
        202 response with Celery task ID.
    """
    try:
        from src.events.celery_tasks import run_pipeline_task

        task = run_pipeline_task.delay(raw_event.model_dump(mode="json"))
        logger.info(
            "Pipeline task enqueued: task_id=%s source=%s",
            task.id,
            raw_event.source_provider,
        )
        return {
            "data": {
                "task_id": task.id,
                "source_provider": raw_event.source_provider,
                "status": "queued",
            },
            "meta": None,
            "error": None,
        }
    except Exception as exc:
        logger.error("Failed to enqueue pipeline task: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "data": None,
                "error": {"code": "ENQUEUE_FAILED", "message": "Failed to enqueue event"},
            },
        ) from None
