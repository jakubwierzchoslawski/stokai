"""
storage.models.earnings_event — SQLAlchemy 2.0 ORM model for earnings_event table.

Stores upcoming/past earnings EPS announcements for portfolio companies.

Table: earnings_event
  earnings_event_id UUID PK
  company_id        UUID NOT NULL FK→company (logical FK)
  tenant_id         UUID NOT NULL
  earnings_date     DATE NOT NULL
  fiscal_quarter    VARCHAR(10) NULL
  expected_eps      FLOAT NULL
  announced_at      TIMESTAMPTZ NULL
  created_at        TIMESTAMPTZ DEFAULT now()
  UNIQUE(company_id, tenant_id, earnings_date)
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = DateTime(timezone=True)  # type: ignore[misc,assignment]


class EarningsEventBase(DeclarativeBase):
    """Declarative base for earnings_event ORM model."""


class EarningsEvent(EarningsEventBase):
    """ORM model for the earnings_event table.

    Multi-tenancy: every query MUST include tenant_id in the WHERE clause.
    """

    __tablename__ = "earnings_event"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "tenant_id", "earnings_date",
            name="uq_earnings_event_company_tenant_date",
        ),
        Index("idx_earnings_event_tenant_date", "tenant_id", "earnings_date"),
    )

    earnings_event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_quarter: Mapped[str | None] = mapped_column(String(10), nullable=True)
    expected_eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    announced_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMPTZ, nullable=True, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"EarningsEvent(earnings_event_id={self.earnings_event_id!r}, "
            f"company_id={self.company_id!r}, earnings_date={self.earnings_date!r})"
        )
