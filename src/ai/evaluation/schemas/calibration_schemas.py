"""
Pydantic v2 schemas for calibration_result and related types.

Provides CalibrationResultCreate, CalibrationResult, CalibrationPassResult,
RegressionReport, and CalibrationSummary.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class CalibrationResultCreate(BaseModel):
    """Input schema for inserting/upserting a calibration result."""

    date: date
    action_signal: str
    total_recommendations: int
    direction_correct_pct: float
    corr_confidence_actual: Optional[float] = None
    mean_confidence: float
    mean_actual_t1d: Optional[float] = None


class CalibrationResult(BaseModel):
    """Response schema for a calibration_result row."""

    result_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    date: date
    action_signal: str
    total_recommendations: int
    direction_correct_pct: float
    corr_confidence_actual: Optional[float] = None
    mean_confidence: float
    mean_actual_t1d: Optional[float] = None
    computed_at: datetime

    model_config = {"from_attributes": True}


class CalibrationPassResult(BaseModel):
    """Result returned from ITier3Calibration.run_calibration()."""

    date: date
    rows_processed: int
    corr_overall: Optional[float] = None
    per_signal: dict[str, CalibrationResult] = Field(default_factory=dict)
    below_threshold: Optional[bool] = None
    threshold_used: float = 0.3
    min_sample_used: int = 30


class RegressionReport(BaseModel):
    """Result returned from ITier2Runner.run_regression().

    passed derives automatically from per_metric_delta: all deltas must be
    >= -0.05 (i.e. no metric regresses by more than 5 %).
    """

    passed: bool = False
    per_metric_delta: dict[str, float] = Field(default_factory=dict)
    breached_metrics: list[str] = Field(default_factory=list)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _derive_passed(self) -> "RegressionReport":
        """Derive passed from per_metric_delta when not explicitly set."""
        if self.per_metric_delta:
            self.breached_metrics = [
                m for m, delta in self.per_metric_delta.items() if delta < -0.05
            ]
            self.passed = len(self.breached_metrics) == 0
        return self


class CalibrationSummary(BaseModel):
    """Aggregated 30-day calibration dashboard summary."""

    days: int
    total_recommendations: int
    per_signal_accuracy: dict[str, float] = Field(default_factory=dict)
    rolling_corr: Optional[float] = None
    below_threshold: bool = False
    assessment: str
