"""
SQLAlchemy 2.0 ORM models for Layer 1 episodic memory tables.

Tables:
  - workflow_run
  - agent_invocation
  - tool_call
  - recommendation_outcome

These are append-only tables (enforced at DB level by triggers in migration 0033).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Float, Integer, Boolean, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, TIMESTAMPTZ
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.ai.memory.models.base import MemoryBase


class WorkflowRun(MemoryBase):
    """Layer 1 episodic: one row per workflow execution."""

    __tablename__ = "workflow_run"

    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    workflow_type: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("NOW()")
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'running'")
    )
    final_state: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, server_default=text("0.0"))
    langfuse_trace_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    agent_invocations: Mapped[list["AgentInvocation"]] = relationship(
        "AgentInvocation", back_populates="workflow_run", lazy="select"
    )
    recommendation_outcomes: Mapped[list["RecommendationOutcome"]] = relationship(
        "RecommendationOutcome", back_populates="workflow_run", lazy="select"
    )


class AgentInvocation(MemoryBase):
    """Layer 1 episodic: one row per agent invocation within a workflow."""

    __tablename__ = "agent_invocation"

    invocation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_run.workflow_id", name="fk_agent_invocation_workflow_run"),
        nullable=False,
    )
    agent_role_id: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("NOW()")
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cost_usd: Mapped[float] = mapped_column(Float, server_default=text("0.0"))
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    output: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    tools_called: Mapped[list[Any]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )

    # Relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="agent_invocations", lazy="select"
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        "ToolCall", back_populates="agent_invocation", lazy="select"
    )


class ToolCall(MemoryBase):
    """Layer 1 episodic: one row per tool call within an agent invocation."""

    __tablename__ = "tool_call"

    tool_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    invocation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "agent_invocation.invocation_id", name="fk_tool_call_agent_invocation"
        ),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    arguments: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_tier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"))
    called_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("NOW()")
    )

    # Relationships
    agent_invocation: Mapped["AgentInvocation"] = relationship(
        "AgentInvocation", back_populates="tool_calls", lazy="select"
    )


class RecommendationOutcome(MemoryBase):
    """
    Layer 1 episodic: calibration outcomes for recommendations.

    This table is partially mutable: actual_t1d, actual_t1w, direction_correct,
    and filled_at may be updated by the Celery outcome-fill task.
    All other columns are append-only (enforced by DB trigger).
    """

    __tablename__ = "recommendation_outcome"

    rec_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "workflow_run.workflow_id", name="fk_recommendation_outcome_workflow_run"
        ),
        nullable=False,
    )
    company_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    action_signal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_t1d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_t1w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direction_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("NOW()")
    )

    # Relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="recommendation_outcomes", lazy="select"
    )
