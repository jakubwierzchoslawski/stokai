"""
FastAPI router for the memory subsystem API.

Endpoints:
  POST   /api/v1/memory/feedback              — any authenticated role; 201
  GET    /api/v1/memory/proposals             — admin only; paginated pending list
  POST   /api/v1/memory/proposals/{id}/approve — admin only
  POST   /api/v1/memory/proposals/{id}/reject  — admin only
  GET    /api/v1/memory/patterns/pending       — admin only
  POST   /api/v1/memory/patterns/{id}/approve  — admin only

Controller responsibility only — no business logic.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import CurrentUser, get_current_user, require_admin
from src.api.memory.memory_schemas import (
    FeedbackRequest,
    FeedbackResponse,
    PatternListResponse,
    PatternResponse,
    ProposalListResponse,
    ProposalResponse,
)
from src.ai.memory.schemas.feedback_schemas import (
    ProposalStatus,
    UserFeedbackCreate,
    FeedbackSource,
)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def _get_memory_service(current_user: CurrentUser) -> "MemoryService":  # noqa: F821
    """
    Build and return a MemoryService from the request context.

    NOTE: In production this would use FastAPI's Depends(get_db_session) and
    DI container. For now it raises NotImplementedError so tests can inject mocks.
    """
    raise NotImplementedError(
        "MemoryService dependency injection is not wired yet. "
        "Wire via get_db_session + DI in main.py."
    )


def _get_procedural_repo():
    raise NotImplementedError("ProceduralRepository DI not wired.")


def _get_improvement_repo():
    raise NotImplementedError("ImprovementRepository DI not wired.")


# ── POST /api/v1/memory/feedback ──────────────────────────────────────────────


@router.post("/feedback", status_code=status.HTTP_201_CREATED, response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    memory_service=Depends(_get_memory_service),
) -> FeedbackResponse:
    """
    Record a user feedback event.

    Any authenticated role (admin, operator, end_user) may submit feedback.
    """
    feedback_create = UserFeedbackCreate(
        tenant_id=current_user.tenant_id,
        report_id=body.report_id,
        recommendation_id=body.recommendation_id,
        feedback_type=body.feedback_type,
        feedback_text=body.feedback_text,
        user_edit=body.user_edit,
        source=body.source,
    )
    result = await memory_service.record_user_feedback(feedback_create)
    return FeedbackResponse(data=result)


# ── GET /api/v1/memory/proposals ──────────────────────────────────────────────


@router.get("/proposals", response_model=ProposalListResponse)
async def list_proposals(
    admin: Annotated[CurrentUser, Depends(require_admin)],
    improvement_repo=Depends(_get_improvement_repo),
) -> ProposalListResponse:
    """Return all pending improvement proposals (admin only)."""
    proposals = await improvement_repo.list_pending()
    return ProposalListResponse(
        data=proposals, meta={"total": len(proposals)}
    )


# ── POST /api/v1/memory/proposals/{id}/approve ────────────────────────────────


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
async def approve_proposal(
    proposal_id: uuid.UUID,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    improvement_repo=Depends(_get_improvement_repo),
) -> ProposalResponse:
    """Approve an improvement proposal (admin only)."""
    updated = await improvement_repo.update_status(
        proposal_id=proposal_id,
        status=ProposalStatus.APPROVED,
        reviewed_by=admin.user_id,
    )
    return ProposalResponse(data=updated)


# ── POST /api/v1/memory/proposals/{id}/reject ─────────────────────────────────


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(
    proposal_id: uuid.UUID,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    improvement_repo=Depends(_get_improvement_repo),
) -> ProposalResponse:
    """Reject an improvement proposal (admin only)."""
    updated = await improvement_repo.update_status(
        proposal_id=proposal_id,
        status=ProposalStatus.REJECTED,
        reviewed_by=admin.user_id,
    )
    return ProposalResponse(data=updated)


# ── GET /api/v1/memory/patterns/pending ──────────────────────────────────────


@router.get("/patterns/pending", response_model=PatternListResponse)
async def list_pending_patterns(
    admin: Annotated[CurrentUser, Depends(require_admin)],
    procedural_repo=Depends(_get_procedural_repo),
) -> PatternListResponse:
    """Return procedural patterns pending human approval (admin only)."""
    patterns = await procedural_repo.list_pending_approval()
    return PatternListResponse(
        data=patterns, meta={"total": len(patterns)}
    )


# ── POST /api/v1/memory/patterns/{id}/approve ─────────────────────────────────


@router.post("/patterns/{pattern_id}/approve", response_model=PatternResponse)
async def approve_pattern(
    pattern_id: uuid.UUID,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    procedural_repo=Depends(_get_procedural_repo),
) -> PatternResponse:
    """Approve a procedural pattern (admin only)."""
    updated = await procedural_repo.approve_pattern(
        pattern_id=pattern_id, approved_by=admin.user_id
    )
    return PatternResponse(data=updated)
