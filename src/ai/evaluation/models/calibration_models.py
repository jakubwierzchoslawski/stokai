"""
SQLAlchemy 2.0 ORM model for the calibration_result table.

Stores daily Tier-3 calibration metrics per action_signal.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Date, Float, Integer, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMPTZ, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.ai.evaluation.models.base import EvaluationBase


class CalibrationResult(EvaluationBase):
    """ORM model for calibration_result table."""

    __tablename__ = "calibration_result"

    result_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid4,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    action_signal: Mapped[str] = mapped_column(String, nullable=False)
    total_recommendations: Mapped[int] = mapped_column(Integer, nullable=False)
    direction_correct_pct: Mapped[float] = mapped_column(Float, nullable=False)
    corr_confidence_actual: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    mean_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    mean_actual_t1d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
    )
