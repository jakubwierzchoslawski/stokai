"""
Pydantic v2 schemas for Layer 1 episodic memory.

Provides request (Create) and response (read) models for all four episodic tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkflowStatus(StrEnum):
    """Valid status values for a workflow run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── WorkflowRun ───────────────────────────────────────────────────────────────


class WorkflowRunCreate(BaseModel):
    """Input schema for creating a new workflow run record."""

    workflow_type: str
    tenant_id: uuid.UUID
    langfuse_trace_id: Optional[str] = None
    cost_usd: float = 0.0


class WorkflowRun(BaseModel):
    """Response schema for a workflow run record."""

    workflow_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    workflow_type: str
    tenant_id: uuid.UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: WorkflowStatus = WorkflowStatus.RUNNING
    final_state: Optional[dict[str, Any]] = None
    cost_usd: float = 0.0
    langfuse_trace_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ── AgentInvocation ───────────────────────────────────────────────────────────


class AgentInvocationCreate(BaseModel):
    """Input schema for creating a new agent invocation record."""

    invocation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    workflow_id: uuid.UUID
    agent_role_id: str
    duration_ms: Optional[int] = None
    model_used: Optional[str] = None
    prompt_version: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    confidence: Optional[float] = None
    output: Optional[dict[str, Any]] = None
    tools_called: list[Any] = Field(default_factory=list)


class AgentInvocation(BaseModel):
    """Response schema for an agent invocation record."""

    invocation_id: uuid.UUID
    workflow_id: uuid.UUID
    agent_role_id: str
    started_at: datetime
    duration_ms: Optional[int] = None
    model_used: Optional[str] = None
    prompt_version: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    confidence: Optional[float] = None
    output: Optional[dict[str, Any]] = None
    tools_called: list[Any] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ── ToolCall ──────────────────────────────────────────────────────────────────


class ToolCallCreate(BaseModel):
    """Input schema for creating a new tool call record."""

    tool_call_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    invocation_id: uuid.UUID
    tool_name: str
    arguments: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None
    cost_tier: Optional[str] = None
    cached: bool = False


class ToolCall(BaseModel):
    """Response schema for a tool call record."""

    tool_call_id: uuid.UUID
    invocation_id: uuid.UUID
    tool_name: str
    arguments: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None
    cost_tier: Optional[str] = None
    cached: bool = False
    called_at: datetime

    model_config = {"from_attributes": True}


# ── RecommendationOutcome ─────────────────────────────────────────────────────


class RecommendationOutcomeCreate(BaseModel):
    """Input schema for creating a new recommendation outcome record."""

    rec_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    workflow_id: uuid.UUID
    company_id: Optional[uuid.UUID] = None
    action_signal: Optional[str] = None
    confidence: Optional[float] = None


class RecommendationOutcome(BaseModel):
    """Response schema for a recommendation outcome record."""

    rec_id: uuid.UUID
    workflow_id: uuid.UUID
    company_id: Optional[uuid.UUID] = None
    action_signal: Optional[str] = None
    confidence: Optional[float] = None
    actual_t1d: Optional[float] = None
    actual_t1w: Optional[float] = None
    direction_correct: Optional[bool] = None
    filled_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
