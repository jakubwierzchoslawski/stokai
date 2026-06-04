"""
Unit tests for ProgressiveDisclosureService.

PLAN-F-020 TASK-003 (TDD)

All tests mock IProgressiveDisclosureRepository. No DB calls are made.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.progressive_disclosure.interfaces.i_progressive_disclosure_repository import (
    AffectedCompanyRow,
    AnalogSummaryRow,
    AuditTrailRow,
    DeepDiveRow,
    PopupDataRow,
    ReasoningStepRow,
    SidePanelDataRow,
    TickerDeltaRow,
)
from src.api.progressive_disclosure.service import (
    DeepDiveNotReadyError,
    EventNotFoundError,
    ProgressiveDisclosureService,
    _time_ago,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

EVENT_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
COMPANY_ID = uuid.uuid4()
NOW = datetime.now(tz=timezone.utc)


def _make_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_popup_data = AsyncMock()
    repo.get_side_panel_data = AsyncMock()
    repo.get_audit_trail = AsyncMock()
    repo.get_deep_dive = AsyncMock()
    repo.get_sparklines = AsyncMock(return_value={})
    return repo


def _popup_row(sample_size: int = 8) -> PopupDataRow:
    return PopupDataRow(
        event_id=EVENT_ID,
        category=["GEOPOLITICAL"],
        intensity=3,
        headline="Test event",
        occurred_at=NOW - timedelta(minutes=5),
        location="Middle East",
        exposed_holdings_count=2,
        tickers_with_delta=[TickerDeltaRow(ticker="AAPL", score_delta=1.5)],
        action_signal="WATCH",
        confidence=0.75,
        sample_size=sample_size,
        low_sample=sample_size < 5,
    )


def _side_panel_row() -> SidePanelDataRow:
    row = _popup_row()
    return SidePanelDataRow(
        event_id=row.event_id,
        category=row.category,
        intensity=row.intensity,
        headline=row.headline,
        occurred_at=row.occurred_at,
        location=row.location,
        exposed_holdings_count=row.exposed_holdings_count,
        tickers_with_delta=row.tickers_with_delta,
        action_signal=row.action_signal,
        confidence=row.confidence,
        sample_size=row.sample_size,
        low_sample=row.low_sample,
        summary="Event summary",
        rationale="Rationale text",
        analogies=[
            AnalogSummaryRow(
                event_id="evt-old",
                headline="Old event",
                occurred_at="2020-01-01",
                similarity_score=0.87,
            )
        ],
        affected_companies=[
            AffectedCompanyRow(
                company_id=COMPANY_ID,
                ticker="AAPL",
                name="Apple Inc",
                score=72.5,
                delta=1.5,
            )
        ],
        is_contrarian=False,
        contrarian_callout=None,
        social_posts=None,
        audit_trail_url=f"/events/{EVENT_ID}/audit-trail",
    )


# ── _time_ago helper ───────────────────────────────────────────────────────────


def test_time_ago_90_seconds() -> None:
    """occurred_at = now - 90s → '1 minute ago'"""
    occurred_at = NOW - timedelta(seconds=90)
    result = _time_ago(occurred_at)
    assert result == "1 minute ago"


def test_time_ago_7200_seconds() -> None:
    """occurred_at = now - 7200s → '2 hours ago'"""
    occurred_at = NOW - timedelta(seconds=7200)
    result = _time_ago(occurred_at)
    assert result == "2 hours ago"


def test_time_ago_just_now() -> None:
    """occurred_at = now → 'just now'"""
    occurred_at = NOW - timedelta(seconds=30)
    result = _time_ago(occurred_at)
    assert result == "just now"


def test_time_ago_plural_minutes() -> None:
    """occurred_at = now - 300s → '5 minutes ago'"""
    occurred_at = NOW - timedelta(seconds=300)
    result = _time_ago(occurred_at)
    assert result == "5 minutes ago"


def test_time_ago_one_day() -> None:
    """occurred_at = now - 86400s → '1 day ago'"""
    occurred_at = NOW - timedelta(days=1)
    result = _time_ago(occurred_at)
    assert result == "1 day ago"


# ── get_popup ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_popup_returns_response_with_time_ago() -> None:
    """get_popup with a valid event returns PopupDataResponse with time_ago formatted."""
    repo = _make_repo()
    repo.get_popup_data.return_value = _popup_row()

    svc = ProgressiveDisclosureService(repo)
    result = await svc.get_popup(EVENT_ID, TENANT_ID)

    assert result.event_id == EVENT_ID
    assert "minute" in result.time_ago or "just now" in result.time_ago
    assert result.action_signal == "WATCH"
    assert result.confidence == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_get_popup_raises_event_not_found() -> None:
    """get_popup with unknown event_id raises EventNotFoundError."""
    repo = _make_repo()
    repo.get_popup_data.return_value = None

    svc = ProgressiveDisclosureService(repo)
    with pytest.raises(EventNotFoundError):
        await svc.get_popup(uuid.uuid4(), TENANT_ID)


# ── get_side_panel ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_side_panel_assembles_sparklines_and_content() -> None:
    """get_side_panel assembles sparklines alongside full analysis content."""
    from src.api.progressive_disclosure.interfaces.i_progressive_disclosure_repository import (
        PricePoint,
    )

    repo = _make_repo()
    repo.get_side_panel_data.return_value = _side_panel_row()
    repo.get_sparklines.return_value = {
        COMPANY_ID: [PricePoint(ts="2026-01-01", close=150.0)]
    }

    svc = ProgressiveDisclosureService(repo)
    result = await svc.get_side_panel(EVENT_ID, TENANT_ID)

    assert result.summary == "Event summary"
    assert result.rationale == "Rationale text"
    assert len(result.analogies) == 1
    assert len(result.sparklines) == 1
    assert result.sparklines[0].ticker == "AAPL"
    assert result.sparklines[0].ohlcv_7d[0].close == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_get_side_panel_contrarian_callout_non_null_when_is_contrarian() -> None:
    """contrarian_callout is non-null when is_contrarian=True."""
    repo = _make_repo()
    row = _side_panel_row()
    row.is_contrarian = True
    row.contrarian_callout = None  # missing — service should fill in
    repo.get_side_panel_data.return_value = row

    svc = ProgressiveDisclosureService(repo)
    result = await svc.get_side_panel(EVENT_ID, TENANT_ID)

    assert result.is_contrarian is True
    assert result.contrarian_callout is not None
    assert len(result.contrarian_callout) > 0


# ── get_audit_trail ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_audit_trail_maps_reasoning_steps_in_order() -> None:
    """get_audit_trail maps agent_invocation rows into ordered ReasoningStepSchema list."""
    repo = _make_repo()
    repo.get_popup_data.return_value = _popup_row()  # ownership check
    repo.get_audit_trail.return_value = AuditTrailRow(
        event_id=EVENT_ID,
        prompt_version="abc123",
        langfuse_trace_url="https://langfuse/traces/xyz",
        analogies=[],
        reasoning_steps=[
            ReasoningStepRow(
                agent_role="event_classifier",
                step_index=0,
                content="Classified as GEOPOLITICAL",
                tool_calls=[],
            ),
            ReasoningStepRow(
                agent_role="recommendation_synthesizer",
                step_index=1,
                content="Signal: WATCH",
                tool_calls=["analogy_lookup"],
            ),
        ],
    )

    svc = ProgressiveDisclosureService(repo)
    result = await svc.get_audit_trail(EVENT_ID, TENANT_ID)

    assert result.prompt_version == "abc123"
    assert len(result.reasoning_steps) == 2
    assert result.reasoning_steps[0].agent_role == "event_classifier"
    assert result.reasoning_steps[1].agent_role == "recommendation_synthesizer"
    assert result.langfuse_trace_url == "https://langfuse/traces/xyz"


# ── get_deep_dive ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_deep_dive_raises_not_ready_when_no_workflow() -> None:
    """get_deep_dive raises DeepDiveNotReadyError when no completed workflow exists."""
    repo = _make_repo()
    repo.get_popup_data.return_value = _popup_row()  # ownership check
    repo.get_deep_dive.return_value = None

    svc = ProgressiveDisclosureService(repo)
    with pytest.raises(DeepDiveNotReadyError):
        await svc.get_deep_dive(EVENT_ID, TENANT_ID)


@pytest.mark.asyncio
async def test_get_deep_dive_returns_response_when_workflow_complete() -> None:
    """get_deep_dive returns DeepDiveResponse when a completed workflow exists."""
    repo = _make_repo()
    repo.get_popup_data.return_value = _popup_row()
    repo.get_deep_dive.return_value = DeepDiveRow(
        event_id=EVENT_ID,
        memo="Full analysis memo text.",
        scenario_tree={
            "label": "Base case",
            "probability": 0.6,
            "description": "Most likely outcome",
            "children": [],
        },
        analogies=[],
        affected_companies=[],
        generated_at=NOW,
    )

    svc = ProgressiveDisclosureService(repo)
    result = await svc.get_deep_dive(EVENT_ID, TENANT_ID)

    assert result.memo == "Full analysis memo text."
    assert result.scenario_tree is not None
    assert result.scenario_tree.label == "Base case"
    assert result.scenario_tree.probability == pytest.approx(0.6)
