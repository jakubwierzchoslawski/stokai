"""
SQLAlchemy 2.0 ORM model for Layer 4 user feedback.

Table: user_feedback
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = DateTime(timezone=True)  # type: ignore[misc,assignment]

from src.ai.memory.models.base import MemoryBase


class UserFeedback(MemoryBase):
    """Layer 4: single user feedback event (HIL action or in-app signal)."""

    __tablename__ = "user_feedback"

    feedback_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    report_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    recommendation_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    feedback_type: Mapped[str] = mapped_column(sa.String(), nullable=False)
    feedback_text: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)
    user_edit: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)
    reviewer_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    source: Mapped[str] = mapped_column(sa.String(), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ(), nullable=False, server_default=text("NOW()")
    )
