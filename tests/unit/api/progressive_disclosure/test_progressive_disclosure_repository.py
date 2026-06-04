"""
Unit tests for ProgressiveDisclosureRepository.

PLAN-F-020 TASK-002 (TDD)

Tests use an AsyncMock session to isolate repository logic from the database.
All tests follow the red→green→refactor cycle mandated by tdd_required: true.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.progressive_disclosure.repositories.progressive_disclosure_repository import (
    ProgressiveDisclosureRepository,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

EVENT_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
COMPANY_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()


def _make_session() -> MagicMock:
    """Return a mock AsyncSession with execute returning empty by default."""
    session = MagicMock()
    session.execute = AsyncMock()
    return session


def _make_execute_result(rows: list[dict]) -> MagicMock:
    """Return a mock result that behaves like SQLAlchemy's MappingResult.

    The mappings() call returns a mock that:
      - .first() → first row or None
      - .all()   → all rows
      - iteration (for row in mappings()) → iterates rows
    """
    result = MagicMock()

    def make_mappings():
        m = MagicMock()
        m.first = MagicMock(return_value=rows[0] if rows else None)
        m.all = MagicMock(return_value=rows)
        # Make the mappings object itself iterable
        m.__iter__ = MagicMock(return_value=iter(rows))
        return m

    result.mappings = MagicMock(side_effect=make_mappings)
    return result


def _make_execute_result_multi(*row_lists: list[dict]):
    """Return a side_effect list for multiple execute() calls."""
    return [_make_execute_result(rows) for rows in row_lists]


# ── get_popup_data ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_popup_data_returns_correct_fields() -> None:
    """get_popup_data with a seeded geo_event + ai_recommendation returns all PopupDataRow fields."""
    session = _make_session()

    popup_row = {
        "event_id": str(EVENT_ID),
        "category": ["GEOPOLITICAL"],
        "intensity": 3,
        "headline": "Test headline",
        "occurred_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        "location": "Middle East",
        "exposed_holdings_count": 2,
        "action_signal": "WATCH",
        "confidence": 0.75,
        "sample_size": 7,
    }
    ticker_rows = [
        {"ticker": "AAPL", "score_delta": 2.5},
        {"ticker": "MSFT", "score_delta": -1.0},
    ]

    session.execute.side_effect = _make_execute_result_multi(
        [popup_row], ticker_rows
    )

    repo = ProgressiveDisclosureRepository(session)
    result = await repo.get_popup_data(EVENT_ID, TENANT_ID)

    assert result is not None
    assert result.headline == "Test headline"
    assert result.action_signal == "WATCH"
    assert result.confidence == pytest.approx(0.75)
    assert result.sample_size == 7
    assert result.low_sample is False
    assert len(result.tickers_with_delta) == 2
    assert result.tickers_with_delta[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_get_popup_data_tenant_mismatch_returns_none() -> None:
    """get_popup_data returns None when tenant_id mismatch (row not returned by DB filter)."""
    session = _make_session()
    # Simulate DB returning no row due to tenant ownership filter
    session.execute.side_effect = _make_execute_result_multi([], [])

    repo = ProgressiveDisclosureRepository(session)
    result = await repo.get_popup_data(EVENT_ID, uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_get_popup_data_low_sample_true_when_sample_size_4() -> None:
    """low_sample=True when sample_size=4 (below threshold of 5)."""
    session = _make_session()

    popup_row = {
        "event_id": str(EVENT_ID),
        "category": ["ECONOMIC"],
        "intensity": 2,
        "headline": "Low sample event",
        "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "location": "Europe",
        "exposed_holdings_count": 1,
        "action_signal": "HOLD",
        "confidence": 0.5,
        "sample_size": 4,  # below threshold
    }
    session.execute.side_effect = _make_execute_result_multi([popup_row], [])

    repo = ProgressiveDisclosureRepository(session)
    result = await repo.get_popup_data(EVENT_ID, TENANT_ID)

    assert result is not None
    assert result.low_sample is True
    assert result.sample_size == 4


@pytest.mark.asyncio
async def test_get_popup_data_low_sample_false_when_sample_size_5() -> None:
    """low_sample=False when sample_size=5 (at threshold)."""
    session = _make_session()

    popup_row = {
        "event_id": str(EVENT_ID),
        "category": ["ECONOMIC"],
        "intensity": 2,
        "headline": "Enough samples",
        "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "location": "Europe",
        "exposed_holdings_count": 1,
        "action_signal": "HOLD",
        "confidence": 0.6,
        "sample_size": 5,  # at threshold — not low
    }
    session.execute.side_effect = _make_execute_result_multi([popup_row], [])

    repo = ProgressiveDisclosureRepository(session)
    result = await repo.get_popup_data(EVENT_ID, TENANT_ID)

    assert result is not None
    assert result.low_sample is False


@pytest.mark.asyncio
async def test_get_popup_data_global_event_accessible_to_any_tenant() -> None:
    """get_popup_data for a global event (tenant_id=NULL) is accessible to any tenant."""
    session = _make_session()

    # Global events have tenant_id IS NULL — DB returns them for any tenant_id
    popup_row = {
        "event_id": str(EVENT_ID),
        "category": ["WEATHER"],
        "intensity": 4,
        "headline": "Global weather event",
        "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "location": "Pacific Ocean",
        "exposed_holdings_count": 5,
        "action_signal": "WATCH",
        "confidence": 0.8,
        "sample_size": 10,
    }
    session.execute.side_effect = _make_execute_result_multi([popup_row], [])

    repo = ProgressiveDisclosureRepository(session)
    # Any tenant_id should work for a global event
    result = await repo.get_popup_data(EVENT_ID, uuid.uuid4())

    assert result is not None
    assert result.headline == "Global weather event"


# ── get_audit_trail ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_audit_trail_orders_steps_by_started_at() -> None:
    """get_audit_trail returns reasoning steps ordered by started_at."""
    session = _make_session()

    run_row = {
        "run_id": str(RUN_ID),
        "langfuse_trace_id": "trace-abc",
    }
    inv_rows = [
        {
            "agent_role": "event_classifier",
            "step_index": 0,
            "output": json.dumps({"content": "Classified as GEOPOLITICAL"}),
            "tool_calls": json.dumps([]),
            "prompt_version": "abc123",
            "started_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
        {
            "agent_role": "recommendation_synthesizer",
            "step_index": 1,
            "output": json.dumps({"content": "Signal: WATCH"}),
            "tool_calls": json.dumps(["analogy_lookup", "portfolio_scorer"]),
            "prompt_version": "def456",
            "started_at": datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc),
        },
    ]
    analog_row = {"analogies": json.dumps([])}

    session.execute.side_effect = _make_execute_result_multi(
        [run_row], inv_rows, [analog_row]
    )

    repo = ProgressiveDisclosureRepository(session)
    result = await repo.get_audit_trail(EVENT_ID)

    assert result is not None
    assert len(result.reasoning_steps) == 2
    assert result.reasoning_steps[0].agent_role == "event_classifier"
    assert result.reasoning_steps[1].agent_role == "recommendation_synthesizer"


@pytest.mark.asyncio
async def test_get_audit_trail_prompt_version_from_synthesizer() -> None:
    """prompt_version matches the recommendation_synthesizer invocation."""
    session = _make_session()

    run_row = {"run_id": str(RUN_ID), "langfuse_trace_id": "trace-xyz"}
    inv_rows = [
        {
            "agent_role": "event_classifier",
            "step_index": 0,
            "output": json.dumps({"content": "Classified"}),
            "tool_calls": json.dumps([]),
            "prompt_version": "aaa111",
            "started_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
        {
            "agent_role": "recommendation_synthesizer",
            "step_index": 1,
            "output": json.dumps({"content": "Synthesized"}),
            "tool_calls": json.dumps([]),
            "prompt_version": "bbb222",
            "started_at": datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc),
        },
    ]
    analog_row = {"analogies": None}

    session.execute.side_effect = _make_execute_result_multi(
        [run_row], inv_rows, [analog_row]
    )

    repo = ProgressiveDisclosureRepository(session)
    result = await repo.get_audit_trail(EVENT_ID)

    assert result is not None
    assert result.prompt_version == "bbb222"


# ── get_sparklines ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_sparklines_returns_7_days_data() -> None:
    """get_sparklines returns close prices bounded to 7 days."""
    session = _make_session()

    price_rows = [
        {"company_id": str(COMPANY_ID), "bar_date": "2026-01-01", "close": 150.0},
        {"company_id": str(COMPANY_ID), "bar_date": "2026-01-02", "close": 152.5},
        {"company_id": str(COMPANY_ID), "bar_date": "2026-01-03", "close": 151.0},
    ]

    result_mock = MagicMock()
    mappings_mock = MagicMock()
    mappings_mock.all = MagicMock(return_value=price_rows)
    result_mock.mappings = MagicMock(return_value=mappings_mock)
    session.execute = AsyncMock(return_value=result_mock)

    repo = ProgressiveDisclosureRepository(session)
    sparklines = await repo.get_sparklines([COMPANY_ID], days=7)

    assert COMPANY_ID in sparklines
    assert len(sparklines[COMPANY_ID]) == 3
    assert sparklines[COMPANY_ID][0].close == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_get_sparklines_empty_for_company_with_no_data() -> None:
    """get_sparklines returns empty list for a company with no price bars."""
    session = _make_session()

    result_mock = MagicMock()
    mappings_mock = MagicMock()
    mappings_mock.all = MagicMock(return_value=[])
    result_mock.mappings = MagicMock(return_value=mappings_mock)
    session.execute = AsyncMock(return_value=result_mock)

    repo = ProgressiveDisclosureRepository(session)
    sparklines = await repo.get_sparklines([COMPANY_ID], days=7)

    assert COMPANY_ID in sparklines
    assert sparklines[COMPANY_ID] == []


# ── get_deep_dive ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_deep_dive_returns_none_when_no_completed_workflow() -> None:
    """get_deep_dive returns None when no event_deep_dive workflow has completed."""
    session = _make_session()

    # First execute: workflow_run returns no row
    # Second execute: should not be called but we mock it empty
    session.execute.side_effect = _make_execute_result_multi([], [])

    repo = ProgressiveDisclosureRepository(session)
    result = await repo.get_deep_dive(EVENT_ID)

    assert result is None
