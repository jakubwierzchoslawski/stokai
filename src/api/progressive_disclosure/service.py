"""
ProgressiveDisclosureService — business logic for the progressive disclosure feature.

PLAN-F-020 TASK-003

Assembles response DTOs from repository data. Handles time_ago computation,
sparkline assembly, contrarian callout enforcement, and deep-dive pending state.

Exceptions:
  EventNotFoundError   — raised when the event does not exist / tenant mismatch → 404
  DeepDiveNotReadyError — raised when no completed deep-dive workflow exists → 202
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

from src.api.progressive_disclosure.interfaces.i_progressive_disclosure_repository import (
    AffectedCompanyRow,
    AnalogSummaryRow,
    IProgressiveDisclosureRepository,
    PricePoint,
    ReasoningStepRow,
)
from src.api.progressive_disclosure.schemas import (
    AffectedCompanySchema,
    AnalogSummarySchema,
    AuditTrailResponse,
    DeepDiveResponse,
    PopupDataResponse,
    ReasoningStepSchema,
    ScenarioNodeSchema,
    SidePanelDataResponse,
    SidePanelApiResponse,
    SocialPostSchema,
    SparklineSchema,
    SparklineSeriesSchema,
    TickerDeltaSchema,
)


# ── Custom exceptions ─────────────────────────────────────────────────────────


class EventNotFoundError(Exception):
    """Raised when an event does not exist or belongs to a different tenant."""

    def __init__(self, event_id: UUID) -> None:
        super().__init__(f"Event {event_id} not found")
        self.event_id = event_id


class DeepDiveNotReadyError(Exception):
    """Raised when no completed event_deep_dive workflow exists for the event."""

    def __init__(self, event_id: UUID) -> None:
        super().__init__(f"Deep dive for event {event_id} is not yet available")
        self.event_id = event_id


# ── Time-ago helper ───────────────────────────────────────────────────────────


def _time_ago(occurred_at: datetime) -> str:
    """Return a human-readable "N minutes/hours ago" string.

    Examples:
        occurred_at = now - 90s  → "1 minute ago"
        occurred_at = now - 7200s → "2 hours ago"
        occurred_at = now - 90000s → "1 day ago"
    """
    now = datetime.now(tz=timezone.utc)
    # Ensure occurred_at is timezone-aware
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    delta = now - occurred_at
    total_seconds = max(int(delta.total_seconds()), 0)

    if total_seconds < 60:
        return "just now"

    minutes = total_seconds // 60
    if minutes < 60:
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit} ago"

    hours = minutes // 60
    if hours < 24:
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit} ago"

    days = hours // 24
    unit = "day" if days == 1 else "days"
    return f"{days} {unit} ago"


# ── Mapper helpers ────────────────────────────────────────────────────────────


def _map_analog(row: AnalogSummaryRow) -> AnalogSummarySchema:
    return AnalogSummarySchema(
        event_id=row.event_id,
        headline=row.headline,
        occurred_at=row.occurred_at,
        similarity_score=row.similarity_score,
    )


def _map_company(row: AffectedCompanyRow) -> AffectedCompanySchema:
    return AffectedCompanySchema(
        company_id=row.company_id,
        ticker=row.ticker,
        name=row.name,
        score=row.score,
        delta=row.delta,
    )


def _map_reasoning_step(row: ReasoningStepRow) -> ReasoningStepSchema:
    return ReasoningStepSchema(
        agent_role=row.agent_role,
        step_index=row.step_index,
        content=row.content,
        tool_calls=row.tool_calls,
    )


def _map_sparkline(company_id: UUID, points: list[PricePoint]) -> SparklineSeriesSchema:
    # ticker is not available from sparkline query; callers pass ticker separately
    return SparklineSeriesSchema(
        ticker=str(company_id),  # fallback; replaced in get_side_panel
        ohlcv_7d=[SparklineSchema(ts=p.ts, close=p.close) for p in points],
    )


def _build_scenario_node(raw: dict) -> ScenarioNodeSchema | None:
    """Recursively build ScenarioNodeSchema from a dict."""
    if not raw:
        return None
    children = [
        c
        for child in raw.get("children", [])
        if (c := _build_scenario_node(child)) is not None
    ]
    return ScenarioNodeSchema(
        label=str(raw.get("label", "")),
        probability=float(raw.get("probability", 0.0)),
        description=str(raw.get("description", "")),
        children=children,
    )


# ── Service ───────────────────────────────────────────────────────────────────


class ProgressiveDisclosureService:
    """Orchestrates data assembly for all four progressive disclosure endpoints."""

    def __init__(self, repository: IProgressiveDisclosureRepository) -> None:
        self._repo = repository

    async def get_popup(
        self, event_id: UUID, tenant_id: UUID
    ) -> PopupDataResponse:
        """Return popup-level data.

        Raises EventNotFoundError when the event does not exist or belongs to a
        different tenant.
        """
        row = await self._repo.get_popup_data(event_id, tenant_id)
        if row is None:
            raise EventNotFoundError(event_id)

        return PopupDataResponse(
            event_id=row.event_id,
            category=row.category,
            intensity=row.intensity,
            headline=row.headline,
            time_ago=_time_ago(row.occurred_at),
            location=row.location,
            exposed_holdings_count=row.exposed_holdings_count,
            tickers_with_delta=[
                TickerDeltaSchema(ticker=t.ticker, score_delta=t.score_delta)
                for t in row.tickers_with_delta
            ],
            action_signal=row.action_signal,
            confidence=row.confidence,
            sample_size=row.sample_size,
            low_sample=row.low_sample,
        )

    async def get_side_panel(
        self, event_id: UUID, tenant_id: UUID
    ) -> SidePanelDataResponse:
        """Return full side-panel data including sparklines.

        Raises EventNotFoundError when not found.
        Ensures contrarian_callout is non-null when is_contrarian=True.
        """
        row = await self._repo.get_side_panel_data(event_id, tenant_id)
        if row is None:
            raise EventNotFoundError(event_id)

        # Fetch sparklines for affected companies
        company_ids = [c.company_id for c in row.affected_companies]
        sparkline_map = await self._repo.get_sparklines(company_ids, days=7)

        # Build sparkline series using ticker from affected_companies
        ticker_by_id = {c.company_id: c.ticker for c in row.affected_companies}
        sparklines = []
        for cid, points in sparkline_map.items():
            ticker = ticker_by_id.get(cid, str(cid))
            sparklines.append(
                SparklineSeriesSchema(
                    ticker=ticker,
                    ohlcv_7d=[SparklineSchema(ts=p.ts, close=p.close) for p in points],
                )
            )

        # Enforce contrarian_callout is non-null when is_contrarian=True
        contrarian_callout = row.contrarian_callout
        if row.is_contrarian and not contrarian_callout:
            contrarian_callout = (
                "Historical analysis indicates this recommendation is contrarian "
                "to the naive interpretation."
            )

        social_posts = (
            [
                SocialPostSchema(
                    post_id=p.post_id,
                    source=p.source,
                    text=p.text,
                    timestamp=p.timestamp,
                )
                for p in row.social_posts
            ]
            if row.social_posts
            else None
        )

        return SidePanelDataResponse(
            event_id=row.event_id,
            category=row.category,
            intensity=row.intensity,
            headline=row.headline,
            time_ago=_time_ago(row.occurred_at),
            location=row.location,
            exposed_holdings_count=row.exposed_holdings_count,
            tickers_with_delta=[
                TickerDeltaSchema(ticker=t.ticker, score_delta=t.score_delta)
                for t in row.tickers_with_delta
            ],
            action_signal=row.action_signal,
            confidence=row.confidence,
            sample_size=row.sample_size,
            low_sample=row.low_sample,
            summary=row.summary,
            sparklines=sparklines,
            rationale=row.rationale,
            analogies=[_map_analog(a) for a in row.analogies],
            affected_companies=[_map_company(c) for c in row.affected_companies],
            is_contrarian=row.is_contrarian,
            contrarian_callout=contrarian_callout,
            social_posts=social_posts,
            audit_trail_url=row.audit_trail_url,
        )

    async def get_audit_trail(
        self, event_id: UUID, tenant_id: UUID
    ) -> AuditTrailResponse:
        """Return audit trail data.

        Performs ownership check via get_popup_data. Raises EventNotFoundError when
        the event does not exist or belongs to a different tenant.
        """
        # Ownership check
        ownership_row = await self._repo.get_popup_data(event_id, tenant_id)
        if ownership_row is None:
            raise EventNotFoundError(event_id)

        trail = await self._repo.get_audit_trail(event_id)
        if trail is None:
            return AuditTrailResponse(
                event_id=event_id,
                prompt_version="",
                langfuse_trace_url="",
                analogies=[],
                reasoning_steps=[],
            )

        return AuditTrailResponse(
            event_id=trail.event_id,
            prompt_version=trail.prompt_version,
            langfuse_trace_url=trail.langfuse_trace_url,
            analogies=[_map_analog(a) for a in trail.analogies],
            reasoning_steps=[_map_reasoning_step(s) for s in trail.reasoning_steps],
        )

    async def get_deep_dive(
        self, event_id: UUID, tenant_id: UUID
    ) -> DeepDiveResponse:
        """Return deep-dive analysis.

        Raises EventNotFoundError when the event does not exist or belongs to a
        different tenant. Raises DeepDiveNotReadyError when no completed deep-dive
        workflow exists (caller returns 202).
        """
        # Ownership check
        ownership_row = await self._repo.get_popup_data(event_id, tenant_id)
        if ownership_row is None:
            raise EventNotFoundError(event_id)

        row = await self._repo.get_deep_dive(event_id)
        if row is None:
            raise DeepDiveNotReadyError(event_id)

        scenario_tree: ScenarioNodeSchema | None = None
        if row.scenario_tree:
            scenario_tree = _build_scenario_node(row.scenario_tree)

        return DeepDiveResponse(
            event_id=row.event_id,
            memo=row.memo,
            scenario_tree=scenario_tree,
            analogies=[_map_analog(a) for a in row.analogies],
            affected_companies=[_map_company(c) for c in row.affected_companies],
            generated_at=row.generated_at,
        )
