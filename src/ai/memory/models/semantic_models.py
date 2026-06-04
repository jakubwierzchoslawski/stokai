"""
SQLAlchemy 2.0 ORM models for Layer 2 semantic memory tables.

Tables:
  - semantic_fact_staging  (pre-gate; evidence_count < 3)
  - semantic_fact          (committed; evidence_count >= 3)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMPTZ
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.ai.memory.models.base import MemoryBase


class SemanticFactStaging(MemoryBase):
    """Pre-gate staging row — held until evidence_count reaches 3."""

    __tablename__ = "semantic_fact_staging"

    staging_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    fact_text: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    evidence_count: Mapped[int] = mapped_column(
        sa.Integer(), nullable=False, server_default=text("1")
    )
    source_invocation_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), server_default=text("'{}'::uuid[]")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ(), nullable=False, server_default=text("NOW()")
    )


class SemanticFact(MemoryBase):
    """Committed semantic fact — evidence_count >= 3 at commit time."""

    __tablename__ = "semantic_fact"

    fact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    fact_text: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536), nullable=True
    )
    evidence_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    last_confirmed: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ(), nullable=False, server_default=text("NOW()")
    )
    decayed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ(), nullable=True)
    retracted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ(), nullable=True)
    retracted_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    source_invocations: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), server_default=text("'{}'::uuid[]")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ(), nullable=False, server_default=text("NOW()")
    )

    @property
    def is_active(self) -> bool:
        """Return True when the fact has not been decayed or retracted."""
        return self.decayed_at is None and self.retracted_at is None
