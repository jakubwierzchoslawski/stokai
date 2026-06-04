"""
API request/response schemas for the evaluation router.

Thin wrappers that expose the relevant Pydantic domain schemas as HTTP
request bodies and query parameters.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EvaluationResultsQuery(BaseModel):
    """Query parameters for listing evaluation results."""

    limit: int = Field(default=100, ge=1, le=1000)


class GoldenDatasetCreateRequest(BaseModel):
    """Request body for POST /evaluation/golden-dataset."""

    input: dict[str, Any]
    expected_output: dict[str, Any]
    quality_metrics: dict[str, Any]
    source: str  # 'hand_authored' | 'admin_override'


class CalibrationQueryParams(BaseModel):
    """Query parameters for calibration endpoints."""

    days: int = Field(default=30, ge=1, le=365)
    action_signal: Optional[str] = None


# ── Calibration Review schemas ────────────────────────────────────────────────


class CalibrationReviewRequest(BaseModel):
    """Request body for POST /evaluation/calibration/reviews."""

    action_taken: Literal[
        "no_action", "improvement_loop_triggered", "model_flag"
    ]
    notes: Optional[str] = None


class CalibrationReviewResponse(BaseModel):
    """Response schema for a calibration review record."""

    review_id: uuid.UUID
    reviewed_by: uuid.UUID
    reviewed_at: datetime
    corr_at_review: Optional[float]
    below_threshold: bool
    action_taken: str
    notes: Optional[str]

    model_config = {"from_attributes": True}
