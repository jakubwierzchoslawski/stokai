"""
SQLAlchemy 2.0 ORM model for Layer 3 procedural memory.

Table: procedural_pattern
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMPTZ
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.ai.memory.models.base import MemoryBase


class ProceduralPattern(MemoryBase):
    """Layer 3: versioned reasoning pattern for an agent role."""

    __tablename__ = "procedural_pattern"

    pattern_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    pattern_type: Mapped[str] = mapped_column(sa.String(), nullable=False)
    context_tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    pattern_text: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    authored_by: Mapped[str] = mapped_column(
        sa.String(), nullable=False, server_default=text("'human'")
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ(), nullable=True)
    approved_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    version: Mapped[int] = mapped_column(
        sa.Integer(), nullable=False, server_default=text("1")
    )
    success_rate: Mapped[Optional[float]] = mapped_column(sa.Float(), nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(sa.Integer(), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(sa.Float(), nullable=True)
    recommended_for_agents: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ(), nullable=False, server_default=text("NOW()")
    )
    retracted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ(), nullable=True)

    @property
    def is_active(self) -> bool:
        """Return True when the pattern is approved and not retracted."""
        return self.approved_at is not None and self.retracted_at is None
