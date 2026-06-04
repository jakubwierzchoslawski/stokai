"""Pydantic v2 schemas for ai_decision audit log.

PLAN-F-029 TASK-002
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AIDecisionCreate(BaseModel):
    """Schema for inserting a new ai_decision row."""

    agent_role: str
    model: str
    prompt_version: str = Field(max_length=40, description="Git SHA (40 chars max)")
    confidence: float = Field(ge=0.0, le=1.0)
    inputs_summary: str = Field(description="First 500 chars of inputs")
    inputs_full: str = Field(description="Complete inputs JSON as text")
    retrieved_analogs: List[Any] = Field(default_factory=list)
    action_signal: Optional[str] = None
    company_ticker: Optional[str] = None
    output_text: str
    langfuse_trace_url: str
    workflow_run_id: Optional[UUID] = None


class AIDecisionRow(BaseModel):
    """Truncated view of an ai_decision row for list responses."""

    decision_id: UUID
    agent_role: str
    model: str
    prompt_version: str
    confidence: float
    inputs_summary: str
    output_text_truncated: str = Field(
        description="output_text truncated to 300 chars"
    )
    action_signal: Optional[str] = None
    company_ticker: Optional[str] = None
    langfuse_trace_url: str
    workflow_run_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, decision: Any) -> "AIDecisionRow":
        return cls(
            decision_id=decision.decision_id,
            agent_role=decision.agent_role,
            model=decision.model,
            prompt_version=decision.prompt_version,
            confidence=decision.confidence,
            inputs_summary=decision.inputs_summary,
            output_text_truncated=(decision.output_text or "")[:300],
            action_signal=decision.action_signal,
            company_ticker=decision.company_ticker,
            langfuse_trace_url=decision.langfuse_trace_url,
            workflow_run_id=decision.workflow_run_id,
            created_at=decision.created_at,
        )


class AIDecisionDetail(BaseModel):
    """Full detail of an ai_decision row — no truncation."""

    decision_id: UUID
    agent_role: str
    model: str
    prompt_version: str
    confidence: float
    inputs_summary: str
    inputs_full: str
    retrieved_analogs: List[Any]
    action_signal: Optional[str] = None
    company_ticker: Optional[str] = None
    output_text: str
    langfuse_trace_url: str
    workflow_run_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DecisionLogFilter(BaseModel):
    """Query filters for the AI decision log list endpoint."""

    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    agent_role: Optional[str] = None
    model: Optional[str] = None
    confidence_min: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_max: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    action_signal: Optional[str] = None
    company_ticker: Optional[str] = None
    cursor: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)
