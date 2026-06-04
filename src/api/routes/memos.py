"""
api.routes.memos — REST endpoint for Event Deep-Dive memos.

GET /api/v1/events/{event_id}/memo
  - JWT auth required.
  - Returns the most recent Brief for the given event_id.
  - 404 if none exists.
  - 200 with MemoResponse if found.
  - tenant_id from JWT is verified against brief.tenant_id (IDOR guard).

PLAN-F-010 TASK-013.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.dependencies import get_current_user, get_db
from src.storage.models.user import User
from src.storage.repositories.brief_repository import BriefRepository

router = APIRouter(prefix="/api/v1", tags=["memos"])


class MemoResponse(BaseModel):
    """Response DTO for the GET /events/{event_id}/memo endpoint."""

    brief_id: UUID
    event_id: UUID
    type: str
    confidence: float
    cost_usd: float
    cost_limited: bool
    content: dict[str, Any]
    created_at: str | None = None


@router.get(
    "/events/{event_id}/memo",
    response_model=MemoResponse,
    summary="Get the most recent Event Deep-Dive memo for an event.",
    responses={
        200: {"description": "Memo found and returned."},
        404: {"description": "No memo exists for the given event_id."},
        401: {"description": "Authentication required."},
    },
)
async def get_event_memo(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoResponse:
    """Return the most recent Brief for a geo event.

    Args:
        event_id: UUID of the geo_event.
        db: Async database session (injected).
        current_user: Authenticated user from JWT (injected).

    Returns:
        MemoResponse with the brief data.

    Raises:
        HTTPException 404: If no brief exists for this event.
        HTTPException 401: If authentication fails.
    """
    repo = BriefRepository(session=db)
    brief = await repo.get_by_event_id(event_id)

    if brief is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "MEMO_NOT_FOUND",
                "message": f"No memo found for event_id={event_id}",
            },
        )

    # IDOR guard: tenant_id in JWT must match brief's tenant_id
    if str(brief.tenant_id) != str(current_user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "MEMO_NOT_FOUND",
                "message": f"No memo found for event_id={event_id}",
            },
        )

    return MemoResponse(
        brief_id=brief.brief_id,
        event_id=brief.event_id,
        type=brief.type,
        confidence=brief.confidence,
        cost_usd=brief.cost_usd,
        cost_limited=brief.cost_limited,
        content=brief.content,
        created_at=(
            brief.created_at.isoformat() if brief.created_at is not None else None
        ),
    )
