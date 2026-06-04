"""
storage.models.brief — SQLAlchemy 2.0 ORM model for the brief/report table.

Stores the output memos produced by the Event Deep-Dive workflow (PLAN-F-010).

Table: brief
  brief_id       UUID PK
  type           VARCHAR(64)         — always "event_deep_dive" for now
  event_id       UUID FK → geo_event
  tenant_id      UUID NOT NULL
  content        JSONB NOT NULL      — full MemoDraft as JSON
  confidence     FLOAT
  cost_usd       FLOAT
  cost_limited   BOOLEAN
  hil_reviewed   BOOLEAN
  hil_approved   BOOLEAN | NULL
  created_at     TIMESTAMPTZ         — server default now()
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BriefBase(DeclarativeBase):
    """Declarative base for the brief table ORM model."""


class Brief(BriefBase):
    """ORM model for the brief table.

    Multi-tenancy: every query MUST include tenant_id in the WHERE clause.
    """

    __tablename__ = "brief"
    __table_args__ = (
        Index("idx_brief_tenant_event", "tenant_id", "event_id"),
    )

    brief_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'event_deep_dive'")
    )
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    cost_limited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    hil_reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    hil_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMPTZ, nullable=True, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"Brief(brief_id={self.brief_id!r}, "
            f"event_id={self.event_id!r}, tenant_id={self.tenant_id!r})"
        )
