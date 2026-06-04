"""
Pydantic v2 schemas for calibration_review table.

Provides CalibrationReviewCreate and CalibrationReview.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

_VALID_ACTIONS = frozenset(
    {"no_action", "improvement_loop_triggered", "model_flag"}
)

ActionTaken = Literal["no_action", "improvement_loop_triggered", "model_flag"]


class CalibrationReviewCreate(BaseModel):
    """Input schema for inserting a calibration review record."""

    reviewed_by: uuid.UUID
    action_taken: str
    corr_at_review: Optional[float] = None
    below_threshold: bool = False
    notes: Optional[str] = None

    @field_validator("action_taken")
    @classmethod
    def validate_action_taken(cls, v: str) -> str:
        if v not in _VALID_ACTIONS:
            raise ValueError(
                f"action_taken must be one of {sorted(_VALID_ACTIONS)}, got {v!r}"
            )
        return v


class CalibrationReview(BaseModel):
    """Response schema for a calibration_review row."""

    review_id: uuid.UUID
    reviewed_by: uuid.UUID
    reviewed_at: datetime
    corr_at_review: Optional[float] = None
    below_threshold: bool
    action_taken: str
    notes: Optional[str] = None

    model_config = {"from_attributes": True}
