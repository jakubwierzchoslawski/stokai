"""
briefs.schemas.brief_schemas — Pydantic domain DTOs for the Briefs Reader.

PLAN-F-026 TASK-001
"""
from __future__ import annotations

import base64
from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class BriefType(StrEnum):
    morning_brief = "morning_brief"
    watchlist_scan = "watchlist_scan"
    earnings_brief = "earnings_brief"
    event_deep_dive = "event_deep_dive"


BRIEF_WORKFLOW_TYPES = [bt.value for bt in BriefType]


class BriefProjection(BaseModel):
    """Projection of workflow_run fields for brief display."""

    brief_id: UUID  # workflow_run.workflow_id
    type: BriefType  # workflow_run.workflow_type
    headline: str  # extracted from final_state JSONB
    content_html: str  # extracted from final_state JSONB
    confidence: float  # extracted from final_state JSONB
    sample_size: int  # extracted from final_state JSONB
    low_sample: bool  # sample_size < 5
    delivery_status: str  # workflow_run.status
    sent_at: Optional[datetime]  # workflow_run.completed_at when dispatched

    model_config = {"from_attributes": True}


class BriefFeedbackCreate(BaseModel):
    """Input schema for submitting brief feedback."""

    feedback_type: str  # "thumbs_up" | "thumbs_down" | "edit"
    correction: Optional[str] = None  # required when feedback_type == "edit"


class BriefListResult(BaseModel):
    """Service-layer result for list_briefs."""

    items: list[BriefProjection]
    next_cursor: Optional[str] = None


class GoldenDatasetCandidateCreate(BaseModel):
    """Input schema for creating a golden dataset candidate."""

    tenant_id: UUID
    brief_id: UUID
    user_id: UUID
    original_content: str
    correction: str


def encode_cursor(completed_at: datetime, workflow_id: UUID) -> str:
    """Encode a cursor from completed_at + workflow_id."""
    raw = f"{completed_at.isoformat()}|{workflow_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode a cursor to (completed_at, workflow_id)."""
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    parts = raw.split("|", 1)
    completed_at = datetime.fromisoformat(parts[0])
    workflow_id = UUID(parts[1])
    return completed_at, workflow_id
