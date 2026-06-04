"""
api.briefs.briefs_schemas — Pydantic request/response models for the Briefs API.

PLAN-F-026 TASK-004
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.briefs.schemas.brief_schemas import BriefType


class BriefListItemResponse(BaseModel):
    """Single item in the briefs list response."""

    brief_id: UUID
    type: BriefType
    date: Optional[datetime]  # sent_at
    headline: str
    confidence: float
    delivery_status: str


class BriefDetailResponse(BaseModel):
    """Full brief detail response."""

    brief_id: UUID
    type: BriefType
    date: Optional[datetime]  # sent_at
    headline: str
    confidence: float
    sample_size: int
    low_sample: bool
    content_html: str
    delivery_status: str


class BriefListDataEnvelope(BaseModel):
    """Data envelope for paginated list."""

    items: list[BriefListItemResponse]
    next_cursor: Optional[str] = None


class BriefListApiResponse(BaseModel):
    """API response for GET /api/v1/briefs."""

    data: BriefListDataEnvelope
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None


class BriefDetailApiResponse(BaseModel):
    """API response for GET /api/v1/briefs/{brief_id}."""

    data: BriefDetailResponse
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None


class FeedbackRequest(BaseModel):
    """Request body for POST /api/v1/briefs/{brief_id}/feedback."""

    feedback_type: str  # "thumbs_up" | "thumbs_down" | "edit"
    correction: Optional[str] = None


class FeedbackResponseData(BaseModel):
    """Data payload for feedback response."""

    feedback_id: UUID


class FeedbackApiResponse(BaseModel):
    """API response for POST /api/v1/briefs/{brief_id}/feedback."""

    data: FeedbackResponseData
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None
