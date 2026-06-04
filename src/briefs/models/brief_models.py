"""
briefs.models.brief_models — SQLAlchemy 2.0 ORM model for GoldenDatasetCandidate.

PLAN-F-026 TASK-001 / TASK-003
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BriefsBase(DeclarativeBase):
    """Declarative base for the briefs module ORM models."""


class GoldenDatasetCandidate(BriefsBase):
    """
    golden_dataset_candidate — stores user edit corrections for AI audit review.

    Written when feedback_type='edit'. Consumed by PLAN-F-029 Admin AI Audit Console.
    """

    __tablename__ = "golden_dataset_candidate"

    candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    brief_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("workflow_run.workflow_id", name="fk_golden_dataset_workflow_run"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    original_content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    correction: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    reviewed: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, server_default=text("FALSE")
    )
    review_notes: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)
