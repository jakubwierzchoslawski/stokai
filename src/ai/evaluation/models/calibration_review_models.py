"""
SQLAlchemy 2.0 ORM model for the calibration_review table.

Stores weekly admin review records for Tier-3 calibration checks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Float, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMPTZ, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.ai.evaluation.models.base import EvaluationBase


class CalibrationReview(EvaluationBase):
    """ORM model for calibration_review table."""

    __tablename__ = "calibration_review"
    __table_args__ = (
        CheckConstraint(
            "action_taken IN ('no_action', 'improvement_loop_triggered', 'model_flag')",
            name="ck_calibration_review_action_taken",
        ),
    )

    review_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid4,
    )
    reviewed_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
    )
    corr_at_review: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    below_threshold: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    action_taken: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
