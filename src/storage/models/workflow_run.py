"""
storage.models.workflow_run — SQLAlchemy 2.0 ORM model for the workflow_run table.

This is the primary workflow run persistence model used by PLAN-F-007.
It extends the base workflow_run definition (from PLAN-F-015 episodic memory)
with the additional columns required for on-demand analysis:
  - user_id  — the user who triggered the analysis
  - company_id — the company being analysed

Migration: alembic/versions/0040_add_workflow_run_analysis_columns.py
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Float, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class WorkflowBase(DeclarativeBase):
    """Declarative base for workflow-level ORM models (storage module)."""


class WorkflowRun(WorkflowBase):
    """
    ORM model for the workflow_run table — extended schema for PLAN-F-007.

    Columns added relative to the episodic-memory initial schema:
      - user_id    UUID NOT NULL
      - company_id UUID

    Multi-tenancy: every lookup MUST include tenant_id in the WHERE clause.
    IDOR prevention is enforced at the repository layer.
    """

    __tablename__ = "workflow_run"
    __table_args__ = (
        Index("idx_workflow_run_tenant", "tenant_id", "workflow_id"),
    )

    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'RUNNING'")
    )
    started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    final_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return (
            f"WorkflowRun(workflow_id={self.workflow_id!r}, "
            f"status={self.status!r}, tenant_id={self.tenant_id!r})"
        )
