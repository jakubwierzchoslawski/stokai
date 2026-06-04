"""
WorkflowState — canonical Pydantic v2 model shared across ALL StokAI workflows.

Every workflow (on_demand, morning_brief, watchlist_scan, earnings_brief,
event_deep_dive) uses this single model as both the LangGraph state and the
serialisation format stored in workflow_run.final_state (JSONB).
"""
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    ON_DEMAND = "on_demand"
    MORNING_BRIEF = "morning_brief"
    WATCHLIST_SCAN = "watchlist_scan"
    EARNINGS_BRIEF = "earnings_brief"
    EVENT_DEEP_DIVE = "event_deep_dive"
    QA = "qa"  # PLAN-F-027: Interactive Q&A sessions


class WorkflowStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COST_LIMIT = "COST_LIMIT"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"       # confidence < 0.4
    HIL_PENDING = "HIL_PENDING"   # confidence 0.4–0.69; awaiting human review
    FAILED = "FAILED"


class WorkflowState(BaseModel):
    """Canonical workflow state model for all StokAI LangGraph workflows."""

    workflow_id: UUID
    workflow_type: WorkflowType
    tenant_id: UUID
    user_id: UUID
    company_id: UUID | None = None  # nullable: QA workflow spans multiple companies
    started_at: datetime
    inputs: dict[str, Any] = Field(default_factory=dict)

    # DeterministicNode outputs
    company_state: dict[str, Any] | None = None
    active_events: list[dict[str, Any]] = Field(default_factory=list)

    # AgentNode outputs
    exposure_output: dict[str, Any] | None = None
    historical_output: dict[str, Any] | None = None
    anomaly_output: dict[str, Any] | None = None
    recommendation: dict[str, Any] | None = None
    report: dict[str, Any] | None = None

    # Confidence tracking
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float | None = None
    requires_hil: bool = False
    hil_reason: str | None = None

    # Cost / token tracking (REQ-N-004)
    cost_usd: float = 0.0
    tokens_consumed: dict[str, int] = Field(default_factory=dict)
    # Set to True by cost_exceeded_node when a workflow is terminated mid-execution
    # due to WorkflowBudgetExceededError (PLAN-N-004).
    cost_limited: bool = False

    # Lifecycle
    status: WorkflowStatus = WorkflowStatus.RUNNING
    error_detail: str | None = None

    # Observability (REQ-N-008)
    langfuse_trace_id: str | None = None
