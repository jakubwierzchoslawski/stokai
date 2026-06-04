"""
api.routers.hil_router — FastAPI router for HIL admin queue endpoints.

Endpoints under /api/v1/admin/hil:
  GET  /                   → list pending items for the authenticated tenant
  GET  /count              → pending item count (for badge display)
  GET  /{item_id}          → item detail + report preview
  POST /{item_id}/action   → apply reviewer action (HILActionRequest body)

Security:
  - JWT auth required on all endpoints (via get_current_user dependency).
  - Role guard: admin | operator only (end_user → 403).
  - tenant_id ALWAYS extracted from JWT claims — never from request body.

Standard success envelope: {"data": ..., "meta": {}, "error": null}
Standard error envelope:   {"data": null, "error": {"code": ..., "message": ...}}

PLAN-F-013 TASK-007
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.ai.hil.hil_action_service import (
    HILActionService,
    UserFeedbackRepository,
)
from src.ai.hil.hil_resume import HILResumeService
from src.api.auth_deps import CurrentUser, get_current_user
from src.api.schemas.hil_schemas import (
    HILActionRequest,
    HILQueueItemDTO,
    HILQueueItemResponse,
    HILQueueListResponse,
    HILQueueCountResponse,
)
from src.config.settings import get_settings
from src.storage.repositories.hil_queue_repository import HILQueueRepository
from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

logger = logging.getLogger(__name__)

hil_router = APIRouter(prefix="/api/v1/admin/hil", tags=["hil-admin"])


# ── Role guard ────────────────────────────────────────────────────────────────

def _require_admin_or_operator(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Raise 403 if the user is not admin or operator."""
    if current_user.role not in ("admin", "operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin or operator role required."},
        )
    return current_user


# ── DB session helper ─────────────────────────────────────────────────────────

@asynccontextmanager
async def _get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a short-lived async session for request-scoped DB access."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _success(data, meta: dict | None = None):  # type: ignore[return]
    """Wrap data in the standard success envelope."""
    return {"data": data, "meta": meta or {}, "error": None}


def _item_to_dto(item) -> HILQueueItemDTO:  # type: ignore[return]
    """Convert an ORM HILQueueItem to a response DTO."""
    return HILQueueItemDTO(
        item_id=item.item_id,
        workflow_run_id=item.workflow_run_id,
        workflow_type=item.workflow_type,
        user_id=item.user_id,
        tenant_id=item.tenant_id,
        confidence=item.confidence,
        scheduled_send_at=item.scheduled_send_at,
        status=item.status,
        reviewer_id=item.reviewer_id,
        reviewed_at=item.reviewed_at,
        lc_checkpoint_id=item.lc_checkpoint_id,
        created_at=item.created_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@hil_router.get(
    "/",
    summary="List pending HIL queue items",
    status_code=status.HTTP_200_OK,
)
async def list_hil_items(
    current_user: CurrentUser = Depends(_require_admin_or_operator),
) -> dict:
    """Return all pending HIL items for the authenticated tenant.

    Items are sorted by scheduled_send_at ascending (most urgent first).
    tenant_id is extracted from the JWT claim — never from the request.

    Returns:
        200 with list of HILQueueItemDTO in standard data envelope.
        403 for end_user role.
    """
    async with _get_db_session() as session:
        repo = HILQueueRepository(session)
        items = await repo.list_pending(current_user.tenant_id)

    dtos = [_item_to_dto(item) for item in items]
    return _success([dto.model_dump() for dto in dtos])


@hil_router.get(
    "/count",
    summary="Pending HIL item count (badge)",
    status_code=status.HTTP_200_OK,
)
async def get_hil_count(
    current_user: CurrentUser = Depends(_require_admin_or_operator),
) -> dict:
    """Return the count of pending HIL items for badge display.

    Polled every 30 s by the admin sidebar (AdminLayout.tsx).

    Returns:
        200 with {"pending_count": int} in data envelope.
    """
    async with _get_db_session() as session:
        repo = HILQueueRepository(session)
        items = await repo.list_pending(current_user.tenant_id)

    return _success({"pending_count": len(items)})


@hil_router.get(
    "/{item_id}",
    summary="Get HIL queue item detail",
    status_code=status.HTTP_200_OK,
)
async def get_hil_item(
    item_id: UUID,
    current_user: CurrentUser = Depends(_require_admin_or_operator),
) -> dict:
    """Return a single HIL queue item including full report preview.

    The WorkflowState.report is available in the item's workflow_run row.
    tenant_id is from JWT — cross-tenant access returns 404 (not 403) to
    prevent IDOR (REQ-N-006).

    Returns:
        200 with HILQueueItemDTO in data envelope.
        403 for end_user role.
        404 when item not found or belongs to a different tenant.
    """
    async with _get_db_session() as session:
        repo = HILQueueRepository(session)
        item = await repo.get(item_id, current_user.tenant_id)

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "HIL queue item not found."},
        )

    return _success(_item_to_dto(item).model_dump())


@hil_router.post(
    "/{item_id}/action",
    summary="Apply a reviewer action to a HIL queue item",
    status_code=status.HTTP_200_OK,
)
async def apply_hil_action(
    item_id: UUID,
    body: HILActionRequest,
    current_user: CurrentUser = Depends(_require_admin_or_operator),
) -> dict:
    """Apply a reviewer action (approve / edit_approve / reject / reject_with_feedback).

    tenant_id is extracted from the JWT — never accepted from the request body.
    Returns 404 (not 403) for cross-tenant item access to prevent IDOR.

    Returns:
        200 with HILActionResponse in data envelope.
        400 for invalid action parameters (missing required fields).
        403 for end_user role.
        404 when item not found or belongs to a different tenant.
    """
    from src.ai.hil.hil_action_service import HILValidationError

    async with _get_db_session() as session:
        hil_repo = HILQueueRepository(session)
        workflow_run_repo = WorkflowRunRepository(session)
        feedback_repo = UserFeedbackRepository(session)
        resume_service = HILResumeService(workflow_run_repo=workflow_run_repo)

        action_service = HILActionService(
            hil_queue_repo=hil_repo,
            resume_service=resume_service,
            feedback_repo=feedback_repo,
            workflow_run_repo=workflow_run_repo,
        )

        try:
            result = await action_service.apply_action(
                item_id=item_id,
                tenant_id=current_user.tenant_id,
                reviewer_id=current_user.user_id,
                action=body.action,
                edited_text=body.edited_text,
                feedback_text=body.feedback_text,
            )
        except HILValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": str(exc)},
            )

        await session.commit()

    response_data = {
        "item_id": str(result.item_id),
        "status": result.status,
        "workflow_resumed": result.workflow_resumed,
        "feedback_id": str(result.feedback_id),
    }
    return _success(response_data)
