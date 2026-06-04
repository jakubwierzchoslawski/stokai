"""
Unit tests for Morning Brief DeterministicNodes.

TDD: written before implementation — PLAN-F-006 TASK-003.

Tests:
  - fetch_portfolio_state: loads positions+watchlist from repo
  - fetch_overnight_events: queries 24h window
  - fetch_score_changes: returns nonzero deltas only
  - fetch_analogies: returns dict keyed by event_id
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.morning_brief_state import MorningBriefState
from src.ai.workflows.morning_brief_nodes import (
    fetch_portfolio_state,
    fetch_overnight_events,
    fetch_score_changes,
    fetch_analogies,
)


def _make_state(**kwargs) -> MorningBriefState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return MorningBriefState(**defaults)


class TestFetchPortfolioState:
    @pytest.mark.asyncio
    async def test_fetch_portfolio_loads_positions_and_watchlist(self):
        """fetch_portfolio_state must load positions and watchlist from repo."""
        state = _make_state()
        repo = MagicMock()
        positions = [{"company_id": str(uuid.uuid4()), "ticker": "AAPL"}]
        watchlist = [{"company_id": str(uuid.uuid4()), "ticker": "MSFT"}]
        repo.get_positions = AsyncMock(return_value=positions)
        repo.get_watchlist = AsyncMock(return_value=watchlist)

        updated = await fetch_portfolio_state(state, portfolio_repo=repo)

        assert updated.portfolio_state is not None
        assert updated.portfolio_state["positions"] == positions
        assert updated.portfolio_state["watchlist"] == watchlist

    @pytest.mark.asyncio
    async def test_fetch_portfolio_calls_repo_with_user_and_tenant(self):
        """fetch_portfolio_state must pass user_id and tenant_id to the repo."""
        state = _make_state()
        repo = MagicMock()
        repo.get_positions = AsyncMock(return_value=[])
        repo.get_watchlist = AsyncMock(return_value=[])

        await fetch_portfolio_state(state, portfolio_repo=repo)

        repo.get_positions.assert_called_once_with(state.user_id, state.tenant_id)
        repo.get_watchlist.assert_called_once_with(state.user_id, state.tenant_id)

    @pytest.mark.asyncio
    async def test_fetch_portfolio_handles_empty_results(self):
        """fetch_portfolio_state must handle None from repo gracefully."""
        state = _make_state()
        repo = MagicMock()
        repo.get_positions = AsyncMock(return_value=None)
        repo.get_watchlist = AsyncMock(return_value=None)

        updated = await fetch_portfolio_state(state, portfolio_repo=repo)

        assert updated.portfolio_state["positions"] == []
        assert updated.portfolio_state["watchlist"] == []


class TestFetchOvernightEvents:
    @pytest.mark.asyncio
    async def test_fetch_events_queries_24h_window(self):
        """fetch_overnight_events must query the event repo for 24h events."""
        state = _make_state()
        repo = MagicMock()
        events = [{"event_id": str(uuid.uuid4()), "title": "Trade dispute"}]
        repo.get_events_in_window = AsyncMock(return_value=events)

        updated = await fetch_overnight_events(state, event_repo=repo)

        assert updated.events == events
        repo.get_events_in_window.assert_called_once_with(
            tenant_id=state.tenant_id,
            hours=24,
        )

    @pytest.mark.asyncio
    async def test_fetch_events_handles_empty_list(self):
        """fetch_overnight_events returns empty list when no events found."""
        state = _make_state()
        repo = MagicMock()
        repo.get_events_in_window = AsyncMock(return_value=[])

        updated = await fetch_overnight_events(state, event_repo=repo)

        assert updated.events == []

    @pytest.mark.asyncio
    async def test_fetch_events_handles_none_from_repo(self):
        """fetch_overnight_events handles None return from repo."""
        state = _make_state()
        repo = MagicMock()
        repo.get_events_in_window = AsyncMock(return_value=None)

        updated = await fetch_overnight_events(state, event_repo=repo)

        assert updated.events == []


class TestFetchScoreChanges:
    @pytest.mark.asyncio
    async def test_fetch_score_changes_returns_nonzero_deltas(self):
        """fetch_score_changes must only return deltas where delta != 0.0."""
        state = _make_state(
            portfolio_state={
                "positions": [{"company_id": str(uuid.uuid4())}],
                "watchlist": [],
            }
        )
        repo = MagicMock()
        changes = [
            {"company_id": "A", "delta": 0.05},
            {"company_id": "B", "delta": 0.0},   # zero — must be filtered
            {"company_id": "C", "delta": -0.12},
        ]
        repo.get_score_changes = AsyncMock(return_value=changes)

        updated = await fetch_score_changes(state, score_repo=repo)

        assert len(updated.score_changes) == 2
        tickers = {c["company_id"] for c in updated.score_changes}
        assert "B" not in tickers

    @pytest.mark.asyncio
    async def test_fetch_score_changes_passes_company_ids(self):
        """fetch_score_changes must extract company_ids from portfolio_state."""
        company_id = str(uuid.uuid4())
        state = _make_state(
            portfolio_state={
                "positions": [{"company_id": company_id}],
                "watchlist": [],
            }
        )
        repo = MagicMock()
        repo.get_score_changes = AsyncMock(return_value=[])

        await fetch_score_changes(state, score_repo=repo)

        call_kwargs = repo.get_score_changes.call_args
        assert company_id in call_kwargs.kwargs["company_ids"]

    @pytest.mark.asyncio
    async def test_fetch_score_changes_handles_no_portfolio_state(self):
        """fetch_score_changes must handle None portfolio_state gracefully."""
        state = _make_state(portfolio_state=None)
        repo = MagicMock()
        repo.get_score_changes = AsyncMock(return_value=[])

        updated = await fetch_score_changes(state, score_repo=repo)

        assert updated.score_changes == []


class TestFetchAnalogies:
    @pytest.mark.asyncio
    async def test_fetch_analogies_returns_dict_keyed_by_event_id(self):
        """fetch_analogies must return a dict keyed by event_id."""
        event_id = str(uuid.uuid4())
        state = _make_state(events=[{"event_id": event_id, "title": "Test"}])
        repo = MagicMock()
        analogies = {event_id: [{"year": 2020, "similarity": 0.9}]}
        repo.get_analogies_for_events = AsyncMock(return_value=analogies)

        updated = await fetch_analogies(state, analogy_repo=repo)

        assert event_id in updated.analogies

    @pytest.mark.asyncio
    async def test_fetch_analogies_returns_empty_dict_when_no_events(self):
        """fetch_analogies returns empty dict when events list is empty."""
        state = _make_state(events=[])
        repo = MagicMock()
        repo.get_analogies_for_events = AsyncMock(return_value={})

        updated = await fetch_analogies(state, analogy_repo=repo)

        assert updated.analogies == {}
        repo.get_analogies_for_events.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_analogies_handles_events_without_event_id(self):
        """fetch_analogies skips events without event_id field."""
        state = _make_state(events=[{"title": "No ID event"}])
        repo = MagicMock()
        repo.get_analogies_for_events = AsyncMock(return_value={})

        updated = await fetch_analogies(state, analogy_repo=repo)

        assert updated.analogies == {}
