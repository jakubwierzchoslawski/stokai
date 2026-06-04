"""
Pydantic v2 schemas for Layer 4 user feedback and improvement proposals.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FeedbackType(StrEnum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    APPROVE = "approve"
    EDIT_APPROVE = "edit_approve"
    REJECT = "reject"
    REJECT_WITH_FEEDBACK = "reject_with_feedback"


class FeedbackSource(StrEnum):
    HIL_ACTION = "hil_action"
    IN_APP = "in_app"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ── UserFeedback ──────────────────────────────────────────────────────────────


class UserFeedbackCreate(BaseModel):
    """Input schema for recording user feedback."""

    tenant_id: uuid.UUID
    report_id: Optional[uuid.UUID] = None
    recommendation_id: Optional[uuid.UUID] = None
    feedback_type: FeedbackType
    feedback_text: Optional[str] = None
    user_edit: Optional[str] = None
    reviewer_id: Optional[uuid.UUID] = None
    source: FeedbackSource = FeedbackSource.IN_APP


class UserFeedback(BaseModel):
    """Response schema for a user feedback record."""

    feedback_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    report_id: Optional[uuid.UUID] = None
    recommendation_id: Optional[uuid.UUID] = None
    feedback_type: str
    feedback_text: Optional[str] = None
    user_edit: Optional[str] = None
    reviewer_id: Optional[uuid.UUID] = None
    source: str
    submitted_at: datetime

    model_config = {"from_attributes": True}


# ── ImprovementProposal ───────────────────────────────────────────────────────


class ImprovementProposalCreate(BaseModel):
    """Input schema for creating an improvement proposal."""

    proposal_type: str
    description: Optional[str] = None
    proposed_changes: Optional[dict[str, Any]] = None
    source_feedback_ids: list[uuid.UUID] = Field(default_factory=list)


class ImprovementProposal(BaseModel):
    """Response schema for an improvement proposal."""

    proposal_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    proposal_type: str
    description: Optional[str] = None
    proposed_changes: Optional[dict[str, Any]] = None
    status: ProposalStatus = ProposalStatus.PENDING
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    source_feedback_ids: list[uuid.UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}
