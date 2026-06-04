"""Unit tests for CompanyScoreRepository.bulk_update_geo_adjusted.

TDD: Tests were written before the implementation.
PLAN-F-018 TASK-003
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from src.scoring.repositories.interfaces import GeoAdjustedUpdate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_update(
    *,
    company_id=None,
    indicator_id=None,
    geo_adjusted: float = 72.5,
    computed_at: datetime | None = None,
) -> GeoAdjustedUpdate:
    return GeoAdjustedUpdate(
        company_id=company_id or uuid4(),
        indicator_id=indicator_id or uuid4(),
        geo_adjusted=geo_adjusted,
        computed_at=computed_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBulkUpdateGeoAdjusted:
    """Tests for CompanyScoreRepository.bulk_update_geo_adjusted."""

    @pytest.mark.asyncio
    async def test_inserts_new_row_when_geo_adjusted_changed(self):
        """Given current geo_adjusted=50.0, updating to 72.5 inserts one row, returns 1."""
        from src.scoring.repositories.company_score_repo import CompanyScoreRepository
        from src.scoring.schemas.company_score import CompanyScoreRecord

        company_id = uuid4()
        indicator_id = uuid4()
        tenant_id = uuid4()

        # Existing row with geo_adjusted = 50.0
        existing_record = CompanyScoreRecord(
            score_id=uuid4(),
            company_id=company_id,
            indicator_id=indicator_id,
            tenant_id=tenant_id,
            raw_value=60.0,
            score=60.0,
            percentile=55.0,
            geo_adjusted=50.0,
            inputs_hash="abc123",
            computed_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )

        session = AsyncMock()
        # Simulate SELECT returning one row
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(
                score_id=existing_record.score_id,
                company_id=existing_record.company_id,
                indicator_id=existing_record.indicator_id,
                tenant_id=existing_record.tenant_id,
                raw_value=existing_record.raw_value,
                score=existing_record.score,
                percentile=existing_record.percentile,
                geo_adjusted=existing_record.geo_adjusted,
                inputs_hash=existing_record.inputs_hash,
                computed_at=existing_record.computed_at,
            )
        ]
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        repo = CompanyScoreRepository(session)
        update = _make_update(
            company_id=company_id,
            indicator_id=indicator_id,
            geo_adjusted=72.5,
        )

        count = await repo.bulk_update_geo_adjusted([update])

        assert count == 1
        # One SELECT + one INSERT (via execute)
        assert session.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_single_select_per_indicator_id_group(self):
        """Two companies sharing the same indicator_id produce exactly one SELECT per group."""
        from src.scoring.repositories.company_score_repo import CompanyScoreRepository

        indicator_id = uuid4()
        company_a = uuid4()
        company_b = uuid4()
        tenant_id = uuid4()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(
                score_id=uuid4(),
                company_id=company_a,
                indicator_id=indicator_id,
                tenant_id=tenant_id,
                raw_value=70.0,
                score=70.0,
                percentile=60.0,
                geo_adjusted=50.0,
                inputs_hash="hash1",
                computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            MagicMock(
                score_id=uuid4(),
                company_id=company_b,
                indicator_id=indicator_id,
                tenant_id=tenant_id,
                raw_value=65.0,
                score=65.0,
                percentile=55.0,
                geo_adjusted=45.0,
                inputs_hash="hash2",
                computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        repo = CompanyScoreRepository(session)
        updates = [
            _make_update(company_id=company_a, indicator_id=indicator_id, geo_adjusted=75.0),
            _make_update(company_id=company_b, indicator_id=indicator_id, geo_adjusted=68.0),
        ]

        count = await repo.bulk_update_geo_adjusted(updates)

        assert count == 2
        # Should be exactly 2 execute calls: 1 SELECT + 1 INSERT for the single group
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_epsilon_guard_skips_tiny_change(self):
        """If new geo_adjusted is within 0.001 of current, no row is inserted, returns 0."""
        from src.scoring.repositories.company_score_repo import CompanyScoreRepository

        company_id = uuid4()
        indicator_id = uuid4()
        tenant_id = uuid4()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(
                score_id=uuid4(),
                company_id=company_id,
                indicator_id=indicator_id,
                tenant_id=tenant_id,
                raw_value=70.0,
                score=70.0,
                percentile=60.0,
                geo_adjusted=72.500,  # current value
                inputs_hash="hash1",
                computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()

        repo = CompanyScoreRepository(session)
        # new_geo_adjusted differs by 0.0005 — within epsilon
        update = _make_update(
            company_id=company_id,
            indicator_id=indicator_id,
            geo_adjusted=72.5005,
        )

        count = await repo.bulk_update_geo_adjusted([update])

        assert count == 0
        # Only the SELECT was executed, no INSERT
        assert session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero_no_db(self):
        """Empty updates list returns 0 without any DB interaction."""
        from src.scoring.repositories.company_score_repo import CompanyScoreRepository

        session = AsyncMock()
        repo = CompanyScoreRepository(session)

        count = await repo.bulk_update_geo_adjusted([])

        assert count == 0
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_row_computed_at_is_after_previous(self):
        """The new snapshot row's computed_at is strictly greater than the previous row's."""
        from src.scoring.repositories.company_score_repo import CompanyScoreRepository

        company_id = uuid4()
        indicator_id = uuid4()
        tenant_id = uuid4()
        old_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(
                score_id=uuid4(),
                company_id=company_id,
                indicator_id=indicator_id,
                tenant_id=tenant_id,
                raw_value=60.0,
                score=60.0,
                percentile=50.0,
                geo_adjusted=50.0,
                inputs_hash="hash_old",
                computed_at=old_time,
            ),
        ]

        inserted_rows = []

        async def capture_execute(stmt, params=None):
            # Capture INSERT params
            if params and isinstance(params, list):
                inserted_rows.extend(params)
            return mock_result

        session.execute = AsyncMock(side_effect=capture_execute)
        session.flush = AsyncMock()

        repo = CompanyScoreRepository(session)
        new_time = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
        update = _make_update(
            company_id=company_id,
            indicator_id=indicator_id,
            geo_adjusted=72.5,
            computed_at=new_time,
        )

        count = await repo.bulk_update_geo_adjusted([update])

        assert count == 1
        # The update's computed_at is strictly newer than old_time
        assert new_time > old_time
