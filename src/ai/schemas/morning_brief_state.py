"""
src.ai.schemas.morning_brief_state — MorningBriefState, BriefRow, ConfidenceRoute, HilStatus.

Canonical Pydantic models and enums for the Morning Brief workflow (PLAN-F-006).

This module re-exports the canonical types from ai.workflows.morning_brief_state
so that downstream consumers can import from either location.

PLAN-F-006 TASK-001
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# Re-export canonical models from the workflow module
from src.ai.workflows.morning_brief_state import (
    ConfidenceRoute,
    MorningBriefState,
    confidence_router,
)


class HilStatus(str, Enum):
    """HIL (Human-in-the-Loop) status for a morning brief row.

    NOT_REQUIRED — brief was auto-sent or blocked; no HIL needed.
    PENDING      — confidence in [0.40, 0.70); awaiting reviewer action.
    APPROVED     — HIL reviewer approved; brief was dispatched.
    REJECTED     — HIL reviewer rejected; brief was withheld.
    TIMED_OUT    — review window expired at 05:45 without action.
    """

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class BriefRow(BaseModel):
    """Data transfer object representing a row in the brief table.

    Used for round-trip serialisation and validation across the workflow.

    PLAN-F-006 TASK-001
    """

    brief_id: UUID = Field(default_factory=uuid4)
    type: str = "morning_brief"
    user_id: UUID
    tenant_id: UUID
    workflow_id: UUID
    content: str  # HTML body of the brief
    confidence: float
    hil_status: HilStatus = HilStatus.NOT_REQUIRED
    sent_at: datetime | None = None
    cost_usd: float = 0.0

    model_config = {"use_enum_values": True}


__all__ = [
    "BriefRow",
    "ConfidenceRoute",
    "HilStatus",
    "MorningBriefState",
    "confidence_router",
]
