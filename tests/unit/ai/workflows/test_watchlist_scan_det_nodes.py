"""
Unit tests for WatchlistScan DeterministicNodes.

TDD: written before implementation — PLAN-F-008 TASK-002.

Nodes tested:
  fetch_scoped_companies  — merges watchlist+portfolio, deduplicates
  fetch_today_events      — filters to scoped companies
  fetch_score_changes     — returns nonzero deltas only
  fetch_analogies         — returns dict keyed by event_id
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.watchlist_scan_nodes import (
    fetch_analogies,
    fetch_score_changes,
    fetch_scoped_companies,
    fetch_today_events,
)
from src.ai.workflows.watchlist_scan_state import WatchlistScanState


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


# ── fetch_scoped_companies ────────────────────────────────────────────────────


class TestFetchScopedCompanies:
    @pytest.mark.asyncio
    async def test_merges_watchlist_and_portfolio(self):
        """scoped_company_ids must be union of watchlist + portfolio."""
        w1, w2 = uuid.uuid4(), uuid.uuid4()
        p1, p2 = uuid.uuid4(), uuid.uuid4()

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[w1, w2])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[p1, p2])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert set(result.scoped_company_ids) == {w1, w2, p1, p2}

    @pytest.mark.asyncio
    async def test_deduplicates_overlapping_companies(self):
        """Companies on both watchlist and portfolio appear only once in scoped."""
        shared = uuid.uuid4()
        other = uuid.uuid4()

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[shared])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[shared, other])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert result.scoped_company_ids.count(shared) == 1
        assert len(result.scoped_company_ids) == 2

    @pytest.mark.asyncio
    async def test_sets_watchlist_companies(self):
        """watchlist_companies field must be set correctly."""
        w1, w2 = uuid.uuid4(), uuid.uuid4()

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[w1, w2])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert result.watchlist_companies == [w1, w2]

    @pytest.mark.asyncio
    async def test_sets_portfolio_companies(self):
        """portfolio_companies field must be set correctly."""
        p1 = uuid.uuid4()

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[p1])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert result.portfolio_companies == [p1]

    @pytest.mark.asyncio
    async def test_result_is_list_not_set(self):
        """scoped_company_ids must be a list (JSON-serializable), not a set."""
        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[uuid.uuid4()])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[uuid.uuid4()])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert isinstance(result.scoped_company_ids, list)

    @pytest.mark.asyncio
    async def test_empty_watchlist_and_portfolio_gives_empty_scoped(self):
        """Empty repos → empty scoped_company_ids."""
        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert result.scoped_company_ids == []


# ── fetch_today_events ────────────────────────────────────────────────────────


class TestFetchTodayEvents:
    @pytest.mark.asyncio
    async def test_returns_events_for_scoped_companies(self):
        """today_events must be populated from geo_event_repo for scoped companies."""
        company_ids = [uuid.uuid4(), uuid.uuid4()]
        event1 = {"event_id": str(uuid.uuid4()), "company_id": str(company_ids[0])}
        event2 = {"event_id": str(uuid.uuid4()), "company_id": str(company_ids[1])}

        geo_event_repo = AsyncMock()
        geo_event_repo.list_for_companies = AsyncMock(return_value=[event1, event2])

        state = _make_state(scoped_company_ids=company_ids)
        result = await fetch_today_events(state, geo_event_repo=geo_event_repo)

        assert result.today_events == [event1, event2]

    @pytest.mark.asyncio
    async def test_passes_scoped_company_ids_to_repo(self):
        """Repo is called with the correct company_ids."""
        company_ids = [uuid.uuid4()]

        geo_event_repo = AsyncMock()
        geo_event_repo.list_for_companies = AsyncMock(return_value=[])

        state = _make_state(scoped_company_ids=company_ids)
        await fetch_today_events(state, geo_event_repo=geo_event_repo)

        call_kwargs = geo_event_repo.list_for_companies.call_args
        assert call_kwargs.kwargs["company_ids"] == company_ids

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_scoped_companies(self):
        """Returns state unchanged when scoped_company_ids is empty."""
        geo_event_repo = AsyncMock()

        state = _make_state(scoped_company_ids=[])
        result = await fetch_today_events(state, geo_event_repo=geo_event_repo)

        assert result.today_events == []
        geo_event_repo.list_for_companies.assert_not_called()


# ── fetch_score_changes ───────────────────────────────────────────────────────


class TestFetchScoreChanges:
    @pytest.mark.asyncio
    async def test_returns_nonzero_deltas_only(self):
        """Only score changes with non-zero delta are returned."""
        company_ids = [uuid.uuid4()]
        changes = [
            {"company_id": str(company_ids[0]), "delta": 5.0},
            {"company_id": str(company_ids[0]), "delta": 0.0},  # must be excluded
            {"company_id": str(company_ids[0]), "delta": -2.0},
        ]

        score_repo = AsyncMock()
        score_repo.list_score_changes = AsyncMock(return_value=changes)

        state = _make_state(scoped_company_ids=company_ids)
        result = await fetch_score_changes(state, score_repo=score_repo)

        assert len(result.score_changes) == 2
        assert all(c["delta"] != 0 for c in result.score_changes)

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_deltas_zero(self):
        """Empty result when all deltas are zero."""
        score_repo = AsyncMock()
        score_repo.list_score_changes = AsyncMock(
            return_value=[{"delta": 0.0}, {"delta": 0}]
        )

        state = _make_state(scoped_company_ids=[uuid.uuid4()])
        result = await fetch_score_changes(state, score_repo=score_repo)

        assert result.score_changes == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_scoped_companies(self):
        """Returns state unchanged when scoped_company_ids is empty."""
        score_repo = AsyncMock()

        state = _make_state(scoped_company_ids=[])
        result = await fetch_score_changes(state, score_repo=score_repo)

        assert result.score_changes == []
        score_repo.list_score_changes.assert_not_called()


# ── fetch_analogies ───────────────────────────────────────────────────────────


class TestFetchAnalogies:
    @pytest.mark.asyncio
    async def test_returns_dict_keyed_by_event_id(self):
        """analogies must be a dict keyed by event_id."""
        event_id_1 = str(uuid.uuid4())
        event_id_2 = str(uuid.uuid4())
        relevant_events = [
            {"event_id": event_id_1},
            {"event_id": event_id_2},
        ]
        analogies_data = {
            event_id_1: [{"analogy": "2008 crash"}],
            event_id_2: [{"analogy": "2020 covid"}],
        }

        analogy_repo = AsyncMock()
        analogy_repo.get_analogies_for_events = AsyncMock(return_value=analogies_data)

        state = _make_state(relevant_events=relevant_events)
        result = await fetch_analogies(state, analogy_repo=analogy_repo)

        assert result.analogies == analogies_data

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_relevant_events(self):
        """Returns state unchanged (empty analogies) when relevant_events is empty."""
        analogy_repo = AsyncMock()

        state = _make_state(relevant_events=[])
        result = await fetch_analogies(state, analogy_repo=analogy_repo)

        assert result.analogies == {}
        analogy_repo.get_analogies_for_events.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_event_ids_to_repo(self):
        """Repo is called with extracted event_ids."""
        event_id = str(uuid.uuid4())
        relevant_events = [{"event_id": event_id, "title": "War in region"}]

        analogy_repo = AsyncMock()
        analogy_repo.get_analogies_for_events = AsyncMock(return_value={})

        state = _make_state(relevant_events=relevant_events)
        await fetch_analogies(state, analogy_repo=analogy_repo)

        call_kwargs = analogy_repo.get_analogies_for_events.call_args
        assert event_id in call_kwargs.kwargs["event_ids"]
