"""SQLAlchemy 2.0 ORM model for the ai_decision audit log table.

PLAN-F-029 TASK-001 / TASK-002

Migration: alembic/versions/0064_ai_decision_table.py
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# TIMESTAMPTZ alias — SQLAlchemy 2.x uses DateTime(timezone=True) for TIMESTAMPTZ
try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = DateTime(timezone=True)  # type: ignore[misc,assignment]


class Base(DeclarativeBase):
    """Declarative base for ai.decision_log ORM models."""


class AIDecision(Base):
    """
    ORM model for the ai_decision table.

    One row per AI decision (classification or recommendation).
    Denormalises agent_role, model, prompt_version, confidence, inputs, and
    output into a single queryable row to serve the Admin AI Audit Console.

    Multi-tenancy note: this table is admin-only; no tenant_id required.
    All access is ADMIN-role-gated at the API layer.
    """

    __tablename__ = "ai_decision"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ai_decision_confidence_range",
        ),
        # Composite index for cursor-based pagination (created_at DESC, decision_id)
        Index(
            "ix_ai_decision_created_at_decision_id",
            sa.text("created_at DESC"),
            "decision_id",
        ),
        Index("ix_ai_decision_agent_role", "agent_role"),
        Index("ix_ai_decision_company_ticker", "company_ticker"),
        Index("ix_ai_decision_action_signal", "action_signal"),
        Index(
            "ix_ai_decision_retrieved_analogs_gin",
            "retrieved_analogs",
            postgresql_using="gin",
        ),
    )

    decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    agent_role: Mapped[str] = mapped_column(String(), nullable=False)
    model: Mapped[str] = mapped_column(String(), nullable=False)
    # git SHA — 40 chars max
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    # First 500 chars of inputs for list view
    inputs_summary: Mapped[str] = mapped_column(Text(), nullable=False)
    # Complete inputs JSON
    inputs_full: Mapped[str] = mapped_column(Text(), nullable=False)
    retrieved_analogs: Mapped[list[Any]] = mapped_column(
        JSONB(), nullable=False, server_default=text("'[]'::jsonb")
    )
    # HOLD | BUY_OPP | etc; null for classification-type decisions
    action_signal: Mapped[str | None] = mapped_column(String(), nullable=True)
    company_ticker: Mapped[str | None] = mapped_column(String(), nullable=True)
    output_text: Mapped[str] = mapped_column(Text(), nullable=False)
    langfuse_trace_url: Mapped[str] = mapped_column(String(), nullable=False)
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_run.workflow_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    def __repr__(self) -> str:
        return (
            f"AIDecision(decision_id={self.decision_id!r}, "
            f"agent_role={self.agent_role!r}, confidence={self.confidence!r})"
        )
