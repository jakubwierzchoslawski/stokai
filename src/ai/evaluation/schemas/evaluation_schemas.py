"""
Pydantic v2 schemas for evaluation_result.

Provides EvaluationResultCreate (input) and EvaluationResult (response).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvaluationResultCreate(BaseModel):
    """Input schema for inserting a new evaluation result."""

    run_id: uuid.UUID
    eval_type: str = "tier_1"
    judge_model: str
    scores: dict[str, Any]
    overall_quality: float = Field(ge=0.0, le=1.0)
    prompt_version: str


class EvaluationResult(BaseModel):
    """Response schema for an evaluation result row."""

    eval_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    run_id: uuid.UUID
    eval_type: str = "tier_1"
    judge_model: str
    scores: dict[str, Any]
    overall_quality: float
    prompt_version: str
    evaluated_at: datetime

    model_config = {"from_attributes": True}
