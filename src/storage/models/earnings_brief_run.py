"""
storage.models.earnings_brief_run — SQLAlchemy 2.0 ORM model for earnings_brief_run table.

Stores each execution of the Earnings Risk Brief workflow including generated
scenario tree, confidence, cost, and HIL status.

Table: earnings_brief_run
  run_id       UUID PK DEFAULT gen_random_uuid()
  workflow_id  UUID NOT NULL FK→workflow_run
  company_id   UUID NOT NULL FK→company (logical FK)
  tenant_id    UUID NOT NULL
  earnings_date DATE NOT NULL
  status        VARCHAR CHECK(status IN ('running','completed','hil','failed'))
  scenario_tree JSONB NULL
  confidence    FLOAT NULL
  cost_usd      FLOAT NULL
  hil_status    VARCHAR DEFAULT 'none' CHECK(hil_status IN ('none','pending','approved','rejected'))
  created_at    TIMESTAMPTZ DEFAULT now()
  UNIQUE(company_id, tenant_id, earnings_date)  -- idempotency guard
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, Float, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class EarningsBriefRunBase(DeclarativeBase):
    """Declarative base for earnings_brief_run ORM model."""


class EarningsBriefRun(EarningsBriefRunBase):
    """ORM model for the earnings_brief_run table.

    Multi-tenancy: every query MUST include tenant_id in the WHERE clause.
    UNIQUE(company_id, tenant_id, earnings_date) prevents duplicate brief runs.
    """

    __tablename__ = "earnings_brief_run"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "tenant_id", "earnings_date",
            name="uq_earnings_brief_run_company_tenant_date",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'hil', 'failed')",
            name="ck_earnings_brief_run_status",
        ),
        CheckConstraint(
            "hil_status IN ('none', 'pending', 'approved', 'rejected')",
            name="ck_earnings_brief_run_hil_status",
        ),
        Index("idx_earnings_brief_run_tenant_company", "tenant_id", "company_id"),
    )

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    workflow_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'running'")
    )
    scenario_tree: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    hil_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'none'")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMPTZ, nullable=True, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"EarningsBriefRun(run_id={self.run_id!r}, "
            f"company_id={self.company_id!r}, status={self.status!r})"
        )
