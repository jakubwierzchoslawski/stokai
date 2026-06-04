"""
API-layer request and response schemas for the memory router.

These are thin wrappers / re-exports of the domain schemas so the API layer
does not directly import service-layer internals.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel

from src.ai.memory.schemas.feedback_schemas import (
    FeedbackSource,
    FeedbackType,
    ImprovementProposal,
    ProposalStatus,
    UserFeedback,
    UserFeedbackCreate,
)
from src.ai.memory.schemas.procedural_schemas import ProceduralPattern


# ── Request schemas ───────────────────────────────────────────────────────────


class FeedbackRequest(BaseModel):
    """POST /api/v1/memory/feedback request body."""

    report_id: Optional[uuid.UUID] = None
    recommendation_id: Optional[uuid.UUID] = None
    feedback_type: FeedbackType
    feedback_text: Optional[str] = None
    user_edit: Optional[str] = None
    source: FeedbackSource = FeedbackSource.IN_APP


class ProposalActionRequest(BaseModel):
    """POST /api/v1/memory/proposals/{id}/approve|reject body (reviewer_id injected from JWT)."""

    pass


# ── Response envelopes ────────────────────────────────────────────────────────


class FeedbackResponse(BaseModel):
    data: UserFeedback
    meta: dict[str, Any] = {}
    error: None = None


class ProposalListResponse(BaseModel):
    data: list[ImprovementProposal]
    meta: dict[str, Any] = {}
    error: None = None


class ProposalResponse(BaseModel):
    data: ImprovementProposal
    meta: dict[str, Any] = {}
    error: None = None


class PatternListResponse(BaseModel):
    data: list[ProceduralPattern]
    meta: dict[str, Any] = {}
    error: None = None


class PatternResponse(BaseModel):
    data: ProceduralPattern
    meta: dict[str, Any] = {}
    error: None = None
