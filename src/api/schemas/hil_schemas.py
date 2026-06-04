"""
api.schemas.hil_schemas — Pydantic request/response DTOs for HIL queue API.

PLAN-F-013 TASK-007
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


# ── Request schemas ───────────────────────────────────────────────────────────


class HILActionRequest(BaseModel):
    """Body for POST /api/v1/admin/hil/{item_id}/action."""

    action: Literal["approve", "edit_approve", "reject", "reject_with_feedback"]
    edited_text: str | None = None    # required when action == "edit_approve"
    feedback_text: str | None = None  # required when action == "reject_with_feedback"


# ── Response schemas ──────────────────────────────────────────────────────────


class HILQueueItemDTO(BaseModel):
    """Single HIL queue item in list or detail responses."""

    item_id: UUID
    workflow_run_id: UUID
    workflow_type: str
    user_id: UUID
    tenant_id: UUID
    confidence: float
    scheduled_send_at: datetime
    status: str
    reviewer_id: UUID | None
    reviewed_at: datetime | None
    lc_checkpoint_id: str
    created_at: datetime | None

    class Config:
        from_attributes = True


class HILQueueListResponse(BaseModel):
    """Envelope for GET /api/v1/admin/hil/ list."""

    data: list[HILQueueItemDTO]
    meta: dict = {}
    error: None = None


class HILQueueCountResponse(BaseModel):
    """Envelope for GET /api/v1/admin/hil/count."""

    data: dict  # {"pending_count": int}
    meta: dict = {}
    error: None = None


class HILActionResponse(BaseModel):
    """Response for POST /api/v1/admin/hil/{item_id}/action."""

    item_id: UUID
    status: str
    workflow_resumed: bool
    feedback_id: UUID


class HILQueueItemResponse(BaseModel):
    """Envelope for GET /api/v1/admin/hil/{item_id}."""

    data: HILQueueItemDTO
    meta: dict = {}
    error: None = None
