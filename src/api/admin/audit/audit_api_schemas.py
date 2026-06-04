"""Pydantic v2 API-layer schemas for Admin AI Audit Console.

PLAN-F-029 TASK-003
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Override ───────────────────────────────────────────────────────────────────

class AdminOverrideRequest(BaseModel):
    """Request body for POST .../decisions/{decision_id}/override."""

    decision_id: UUID
    corrected_output: str = Field(min_length=10)
    override_reason: str = Field(min_length=20)


class AdminOverrideResponse(BaseModel):
    """Response for a successful admin override."""

    decision_id: UUID
    feedback_id: UUID
    golden_dataset_candidate_id: UUID
    proposed_prompt_adjustment: str
    status: str = "pending_review"


# ── Prompt version history ─────────────────────────────────────────────────────

class PromptVersionEntry(BaseModel):
    """One row in the prompt version history table."""

    version_id: str = Field(description="Git SHA")
    agent_role: str
    label_applied: str
    published_at: datetime
    rolled_back_at: Optional[datetime] = None
    quality_metrics: Optional[Dict[str, Any]] = None


class RollbackRequest(BaseModel):
    """Request body for POST .../prompts/{agent_role}/rollback."""

    agent_role: str
    to_version: str = Field(description="Git SHA to roll back to")


class RollbackResponse(BaseModel):
    """Response for a successful prompt rollback."""

    agent_role: str
    previous_version: str
    rolled_back_to: str
    effective_at: datetime


# ── Workflow history ───────────────────────────────────────────────────────────

class ToolCallSummary(BaseModel):
    """Summary of a single tool call within an agent invocation."""

    tool_call_id: UUID
    tool_name: str
    duration_ms: int
    cost_tier: Optional[str] = None
    cached: bool = False


class AgentInvocationSummary(BaseModel):
    """Summary of one agent invocation within a workflow run."""

    invocation_id: UUID
    agent_role_id: str
    model_used: str
    prompt_version: str
    confidence: Optional[float] = None
    cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int
    tool_calls: List[ToolCallSummary] = Field(default_factory=list)


class WorkflowRunSummary(BaseModel):
    """Summary row for workflow history list."""

    workflow_id: UUID
    workflow_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    cost_usd: float
    langfuse_trace_id: Optional[str] = None


class WorkflowRunDetail(WorkflowRunSummary):
    """Full detail including agent invocations and tool calls."""

    agent_invocations: List[AgentInvocationSummary] = Field(default_factory=list)
    final_state: Optional[Dict[str, Any]] = None


class RerunRequest(BaseModel):
    """Request body for POST .../workflows/{workflow_id}/rerun."""

    workflow_id: UUID


class RerunResponse(BaseModel):
    """Response for a successful workflow re-run dispatch."""

    new_workflow_id: UUID
    workflow_type: str
    dispatched_at: datetime


# ── Calibration pass-through ───────────────────────────────────────────────────

class CalibrationResult(BaseModel):
    """One calibration result row (from calibration_result table)."""

    result_id: UUID
    action_signal: str
    window_days: int
    corr_confidence_actual: float
    direction_correct_pct: float
    mean_confidence: float
    total_recommendations: int
    computed_at: datetime
    below_threshold: bool


class PerSignalAccuracy(BaseModel):
    action_signal: str
    direction_correct_pct: float
    mean_confidence: float
    total_recommendations: int


class CalibrationSummary(BaseModel):
    """Aggregated calibration summary for the dashboard."""

    window_days: int
    below_threshold: bool
    threshold: float
    per_signal_accuracy: List[PerSignalAccuracy] = Field(default_factory=list)
    computed_at: datetime
