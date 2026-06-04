"""
ai.workflows.earnings_brief.state — EarningsBriefState and ScenarioTree models.

PLAN-F-009 TASK-003
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


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
    analogies: list[dict] = Field(default_factory=list)
    macro_summary: str
    sector_summary: str

    @validator("bear", always=True)
    def probabilities_sum_to_one(
        cls, bear: EarningsScenario, values: dict
    ) -> EarningsScenario:
        """Ensure bull + base + bear probabilities sum to 1.0 ± 0.01."""
        bull = values.get("bull")
        base = values.get("base")
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
    PLAN-F-009 TASK-003
    """

    workflow_id: UUID
    workflow_type: str = "earnings_brief"
    tenant_id: UUID
    user_id: UUID
    company_id: UUID
    earnings_date: date
    started_at: datetime

    # DeterministicNode outputs
    company_state: dict | None = None
    earnings_history: list[dict] = Field(default_factory=list)
    macro_context: dict | None = None
    sector_recent_earnings: list[dict] = Field(default_factory=list)

    # AgentNode outputs
    scenario_tree: ScenarioTree | None = None
    analogies_output: dict | None = None
    recommendation: dict | None = None
    report: dict | None = None

    # Confidence tracking
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float | None = None
    requires_hil: bool = False

    # Cost tracking (REQ-N-004)
    cost_usd: float = 0.0

    # Observability (REQ-N-008)
    langfuse_trace_id: str | None = None
