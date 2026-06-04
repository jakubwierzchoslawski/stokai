"""
API request/response schemas for the evaluation router.

Thin wrappers that expose the relevant Pydantic domain schemas as HTTP
request bodies and query parameters.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

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
