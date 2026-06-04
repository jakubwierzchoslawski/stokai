"""
storage.models.brief — SQLAlchemy 2.0 ORM model for the brief/report table.

Stores the output memos produced by the Event Deep-Dive workflow (PLAN-F-010)
and Morning Brief workflow (PLAN-F-006).

Table: brief
  brief_id       UUID PK
  type           VARCHAR(64)         — always "event_deep_dive" for now (legacy)
  brief_type     VARCHAR(64)         — morning_brief/watchlist_scan/earnings_brief/event_deep_dive
  event_id       UUID FK → geo_event (nullable for non-event-deep-dive briefs)
  user_id        UUID                — user who owns this brief
  workflow_id    UUID                — FK to workflow_run
  tenant_id      UUID NOT NULL
  content        JSONB NOT NULL      — full MemoDraft as JSON
  confidence     FLOAT
  hil_status     VARCHAR(16)         — none/pending/approved/rejected
  sent_at        TIMESTAMPTZ         — when email was dispatched
  cost_usd       FLOAT
  cost_limited   BOOLEAN
  hil_reviewed   BOOLEAN
  hil_approved   BOOLEAN | NULL
  created_at     TIMESTAMPTZ         — server default now()

Migration:
  - 0057_add_morning_brief_columns.py adds brief_type, user_id, workflow_id,
    hil_status, and sent_at columns.
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
        Index("idx_brief_user_tenant_type", "user_id", "tenant_id", "brief_type"),
    )

    brief_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'event_deep_dive'")
    )
    # Extended column for morning brief (PLAN-F-006)
    brief_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, server_default=text("'event_deep_dive'")
    )
    event_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    # Morning brief owner
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    # Workflow that produced this brief
    workflow_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    # HIL status for morning brief (replaces hil_reviewed/hil_approved booleans)
    hil_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, server_default=text("'none'")
    )
    # When the email was dispatched
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
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
            f"brief_type={self.brief_type!r}, tenant_id={self.tenant_id!r})"
        )
