"""
storage.models.ai_recommendation — SQLAlchemy 2.0 ORM model for the ai_recommendation table.

Stores AI-generated recommendations produced by on-demand and event deep-dive workflows.
For on-demand runs, event_id is NULL (the recommendation applies to the company overall).
For event deep-dive runs, event_id links to the triggering geo_event row.

PLAN-F-007 TASK-010
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = DateTime(timezone=True)  # type: ignore[misc,assignment]


class AiRecommendationBase(DeclarativeBase):
    """Declarative base for AI recommendation ORM models.

    Separate from WorkflowBase so the SQLite in-memory tests for workflow_run
    do not attempt to create the ai_recommendation table schema.
    """


class AiRecommendation(AiRecommendationBase):
    """ORM model for the ai_recommendation table.

    Attributes:
        recommendation_id  — PK UUID.
        workflow_id        — FK to workflow_run.workflow_id.
        tenant_id          — Tenant scope (multi-tenancy guard).
        company_id         — The company the recommendation pertains to.
        event_id           — NULL for on-demand runs; set for event deep-dive runs.
        workflow_type      — String label: "on_demand" | "event_deep_dive" etc.
        recommendation     — JSONB payload from WorkflowState.recommendation.
        overall_confidence — Numeric confidence score from evaluate_quality node.
        status             — Workflow terminal status at time of save.
        created_at         — Timestamp of row creation.
    """

    __tablename__ = "ai_recommendation_v2"

    recommendation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workflow_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    overall_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    status: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"AiRecommendation(recommendation_id={self.recommendation_id!r}, "
            f"company_id={self.company_id!r})"
        )
