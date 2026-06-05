"""
SQLAlchemy 2.0 ORM model for the evaluation_result table.

Stores Tier-1 judge outputs produced by Tier1JudgeService.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = DateTime(timezone=True)  # type: ignore[misc,assignment]

from src.ai.evaluation.models.base import EvaluationBase


class EvaluationResult(EvaluationBase):
    """ORM model for evaluation_result table."""

    __tablename__ = "evaluation_result"

    eval_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid4,
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    eval_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'tier_1'"),
    )
    judge_model: Mapped[str] = mapped_column(String, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    overall_quality: Mapped[float] = mapped_column(Float, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
    )
