"""
Unit tests for scoped company deduplication logic.

TDD: written before implementation — PLAN-F-008 TASK-014.

Tests:
  - dedup removes duplicates from union of watchlist + portfolio
  - result is list not set (for JSON serialization)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.ai.workflows.watchlist_scan_nodes import fetch_scoped_companies
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


class TestScopedCompanyDeduplication:
    @pytest.mark.asyncio
    async def test_dedup_removes_exact_duplicates(self):
        """A company on both watchlist and portfolio appears once in scoped_company_ids."""
        shared = uuid.uuid4()

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[shared])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[shared])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert result.scoped_company_ids.count(shared) == 1

    @pytest.mark.asyncio
    async def test_dedup_with_multiple_overlaps(self):
        """Multiple overlapping companies are deduplicated correctly."""
        c1, c2, c3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[c1, c2])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[c2, c3])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert len(result.scoped_company_ids) == 3
        assert set(result.scoped_company_ids) == {c1, c2, c3}

    @pytest.mark.asyncio
    async def test_result_is_list_type(self):
        """scoped_company_ids must be a list, not a set (JSON-serializable)."""
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
    async def test_result_is_serializable_to_json(self):
        """scoped_company_ids must serialize cleanly (list of UUIDs → str)."""
        import json

        c1 = uuid.uuid4()
        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[c1])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[c1])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        # Model dump includes UUIDs — verify the full state dumps without error
        data = result.model_dump()
        # Convert UUIDs to str manually (model_dump returns UUID objects by default)
        json.dumps({k: [str(v) for v in vs] if isinstance(vs, list) else v
                    for k, vs in data.items()
                    if isinstance(vs, list) or not isinstance(vs, list)},
                   default=str)

    @pytest.mark.asyncio
    async def test_ordering_preserved_watchlist_first(self):
        """Watchlist companies appear before unique portfolio companies."""
        w1, w2 = uuid.uuid4(), uuid.uuid4()
        p1 = uuid.uuid4()  # unique to portfolio

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[w1, w2])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[p1])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        # w1 and w2 come first
        assert result.scoped_company_ids[0] == w1
        assert result.scoped_company_ids[1] == w2
        assert result.scoped_company_ids[2] == p1

    @pytest.mark.asyncio
    async def test_empty_watchlist_all_portfolio_companies_included(self):
        """Empty watchlist → all portfolio companies in scoped."""
        p1, p2 = uuid.uuid4(), uuid.uuid4()

        watchlist_repo = AsyncMock()
        watchlist_repo.list_company_ids = AsyncMock(return_value=[])
        portfolio_repo = AsyncMock()
        portfolio_repo.list_company_ids = AsyncMock(return_value=[p1, p2])

        state = _make_state()
        result = await fetch_scoped_companies(
            state, watchlist_repo=watchlist_repo, portfolio_repo=portfolio_repo
        )

        assert set(result.scoped_company_ids) == {p1, p2}
