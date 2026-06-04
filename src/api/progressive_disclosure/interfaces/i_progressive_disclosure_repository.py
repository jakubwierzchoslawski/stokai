"""
IProgressiveDisclosureRepository — abstract interface for progressive disclosure data access.

PLAN-F-020 TASK-002

Reads from existing tables: geo_event, ai_recommendation, event_exposure, company,
agent_invocation, workflow_run, price_bar. No new tables are created.

IDOR prevention: all event lookups filter by tenant_id (NULL = global, visible to all).
A foreign event_id returns no row (callers raise 404, not 403).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


# ── Data-transfer objects (row-level, schema-free) ─────────────────────────────
# These are plain dataclasses used as the contract between the repository and the
# service layer. Pydantic response schemas are defined in schemas.py.


@dataclass
class TickerDeltaRow:
    ticker: str
    score_delta: float


@dataclass
class PopupDataRow:
    event_id: UUID
    category: list[str]
    intensity: int
    headline: str
    occurred_at: datetime
    location: str
    exposed_holdings_count: int
    tickers_with_delta: list[TickerDeltaRow]
    action_signal: str
    confidence: float
    sample_size: int
    low_sample: bool


@dataclass
class AnalogSummaryRow:
    event_id: str
    headline: str
    occurred_at: str
    similarity_score: float


@dataclass
class AffectedCompanyRow:
    company_id: UUID
    ticker: str
    name: str
    score: float
    delta: float


@dataclass
class SocialPostRow:
    post_id: str
    source: str
    text: str
    timestamp: str


@dataclass
class SidePanelDataRow(PopupDataRow):
    summary: str = ""
    rationale: str = ""
    analogies: list[AnalogSummaryRow] = field(default_factory=list)
    affected_companies: list[AffectedCompanyRow] = field(default_factory=list)
    is_contrarian: bool = False
    contrarian_callout: str | None = None
    social_posts: list[SocialPostRow] | None = None
    audit_trail_url: str = ""


@dataclass
class ReasoningStepRow:
    agent_role: str
    step_index: int
    content: str
    tool_calls: list[str]


@dataclass
class AuditTrailRow:
    event_id: UUID
    prompt_version: str
    langfuse_trace_url: str
    analogies: list[AnalogSummaryRow]
    reasoning_steps: list[ReasoningStepRow]


@dataclass
class PricePoint:
    ts: str   # ISO date
    close: float


@dataclass
class DeepDiveRow:
    event_id: UUID
    memo: str
    scenario_tree: dict | None
    analogies: list[AnalogSummaryRow]
    affected_companies: list[AffectedCompanyRow]
    generated_at: datetime


# ── Abstract interface ─────────────────────────────────────────────────────────


class IProgressiveDisclosureRepository(ABC):
    """Abstract repository for progressive disclosure data access.

    All event lookups enforce tenant_id ownership:
    ``geo_event.tenant_id IS NULL OR geo_event.tenant_id = :tenant_id``.
    A foreign event_id returns None; callers raise EventNotFoundError (404).
    """

    @abstractmethod
    async def get_popup_data(
        self, event_id: UUID, tenant_id: UUID
    ) -> PopupDataRow | None:
        """Return popup-level data for an event.

        Enforces tenant ownership. Returns None when event is not found or
        belongs to a different tenant.
        """
        ...

    @abstractmethod
    async def get_side_panel_data(
        self, event_id: UUID, tenant_id: UUID
    ) -> SidePanelDataRow | None:
        """Return full side-panel data including rationale, analogies, and sparkline inputs.

        Enforces tenant ownership. Returns None when not found.
        """
        ...

    @abstractmethod
    async def get_audit_trail(self, event_id: UUID) -> AuditTrailRow | None:
        """Return audit trail data: reasoning steps, prompt SHA, Langfuse trace.

        Ownership is pre-checked via get_popup_data before calling this.
        Returns None when no workflow run exists for the event.
        """
        ...

    @abstractmethod
    async def get_deep_dive(self, event_id: UUID) -> DeepDiveRow | None:
        """Return completed deep-dive workflow output for the event.

        Returns None when no ``event_deep_dive`` workflow has completed for
        the event (triggers 202 Accepted in the router).
        """
        ...

    @abstractmethod
    async def get_sparklines(
        self, company_ids: list[UUID], days: int = 7
    ) -> dict[UUID, list[PricePoint]]:
        """Return T±days price data for a set of companies.

        Bounded to ``days * len(company_ids) ≤ 700`` rows.
        Returns an empty list for companies with no price_bar data.
        """
        ...
