"""
ai.workflows.earnings_brief.state — EarningsBriefState and ScenarioTree models.

PLAN-F-009 TASK-002
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.ai.workflows.state import WorkflowStatus


class EarningsScenario(BaseModel):
    """A single bull / base / bear earnings scenario."""

    probability: float = Field(ge=0.0, le=1.0)
    rationale: str
    macro_drivers: list[str]
    sector_drivers: list[str]
    implied_price_impact_pct: float | None = None


class ScenarioTree(BaseModel):
    """Three-scenario earnings tree with probability-sum validation.

    Validator: bull.probability + base.probability + bear.probability = 1.0 ± 0.01.
    """

    bull: EarningsScenario
    base: EarningsScenario
    bear: EarningsScenario
    analogies: list[dict[str, Any]] = Field(default_factory=list)
    macro_summary: str
    sector_summary: str

    @field_validator("bear")
    @classmethod
    def probabilities_sum_to_one(cls, bear: EarningsScenario, info: Any) -> EarningsScenario:
        """Ensure bull + base + bear probabilities sum to 1.0 ± 0.01."""
        data = info.data
        bull = data.get("bull")
        base = data.get("base")
        if bull and base:
            total = bull.probability + base.probability + bear.probability
            if abs(total - 1.0) > 0.01:
                raise ValueError(
                    f"Scenario probabilities must sum to 1.0 ± 0.01, got {total}"
                )
        return bear


class EarningsBriefState(BaseModel):
    """LangGraph state for the Earnings Risk Brief workflow.

    Passed through all nodes and serialised as JSONB in earnings_brief_run.
    PLAN-F-009 TASK-002
    """

    workflow_id: UUID
    workflow_type: str = "earnings_brief"
    tenant_id: UUID
    user_id: UUID
    company_id: UUID
    earnings_date: date
    started_at: datetime
    inputs: dict[str, Any] = Field(default_factory=dict)

    # DeterministicNode outputs
    company_state: dict[str, Any] | None = None
    earnings_history: list[dict[str, Any]] = Field(default_factory=list)
    macro_context: dict[str, Any] | None = None
    sector_recent_earnings: list[dict[str, Any]] = Field(default_factory=list)

    # AgentNode outputs
    scenario_tree: ScenarioTree | None = None
    analogies_output: dict[str, Any] | None = None
    recommendation: dict[str, Any] | None = None
    report: dict[str, Any] | None = None

    # Confidence tracking
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float | None = None
    requires_hil: bool = False
    hil_reason: str | None = None

    # Cost tracking (REQ-N-004)
    cost_usd: float = 0.0
    tokens_consumed: dict[str, int] = Field(default_factory=dict)

    # Workflow status and routing
    status: WorkflowStatus = WorkflowStatus.RUNNING
    error_detail: str | None = None

    # Observability
    langfuse_trace_id: str | None = None
