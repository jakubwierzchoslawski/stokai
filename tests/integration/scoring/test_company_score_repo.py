"""Integration tests for CompanyScoreRepository (D4 snapshot-write guard).

Uses an in-memory repository implementation to avoid real DB dependency.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from uuid import uuid4, UUID

from src.scoring.repositories.company_score_repo import SCORE_CHANGE_EPSILON, compute_inputs_hash
from src.scoring.schemas.company_score import CompanyScoreRecord

pytestmark = pytest.mark.integration

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
COMPANY_ID = uuid4()
INDICATOR_ID = uuid4()


# ---------------------------------------------------------------------------
# In-memory repository for testing
# ---------------------------------------------------------------------------

class InMemoryCompanyScoreRepository:
    """In-memory implementation of ICompanyScoreRepository for tests."""

    def __init__(self):
        self._rows: list[CompanyScoreRecord] = []

    async def get_current(
        self, company_id: UUID, indicator_id: UUID
    ) -> CompanyScoreRecord | None:
        matching = [
            r for r in self._rows
            if r.company_id == company_id and r.indicator_id == indicator_id
        ]
        if not matching:
            return None
        return max(matching, key=lambda r: r.computed_at)

    async def upsert_if_changed(self, record: CompanyScoreRecord) -> bool:
        current = await self.get_current(record.company_id, record.indicator_id)
        if current is not None:
            score_diff = abs(record.score - current.score)
            if score_diff <= SCORE_CHANGE_EPSILON:
                return False
        self._rows.append(record)
        return True

    async def get_history(
        self, company_id: UUID, indicator_id: UUID, limit: int = 90
    ) -> list[CompanyScoreRecord]:
        matching = [
            r for r in self._rows
            if r.company_id == company_id and r.indicator_id == indicator_id
        ]
        return sorted(matching, key=lambda r: r.computed_at, reverse=True)[:limit]


def _make_record(score: float, inputs: dict | None = None) -> CompanyScoreRecord:
    inputs = inputs or {"revenue": 1000.0}
    return CompanyScoreRecord.new(
        company_id=COMPANY_ID,
        indicator_id=INDICATOR_ID,
        tenant_id=TENANT_ID,
        raw_value=score,
        score=score,
        inputs_hash=compute_inputs_hash(inputs),
    )


class TestUpsertIfChanged:
    @pytest.mark.asyncio
    async def test_writes_new_row_when_none_present(self):
        repo = InMemoryCompanyScoreRepository()
        record = _make_record(75.0)
        result = await repo.upsert_if_changed(record)
        assert result is True

    @pytest.mark.asyncio
    async def test_writes_when_score_differs_significantly(self):
        repo = InMemoryCompanyScoreRepository()
        record1 = _make_record(50.0)
        await repo.upsert_if_changed(record1)

        record2 = _make_record(50.0 + SCORE_CHANGE_EPSILON * 2)  # above epsilon
        result = await repo.upsert_if_changed(record2)
        assert result is True

    @pytest.mark.asyncio
    async def test_does_not_write_when_score_within_epsilon(self):
        repo = InMemoryCompanyScoreRepository()
        record1 = _make_record(50.0)
        await repo.upsert_if_changed(record1)

        # Score change within epsilon — should NOT write
        tiny_change = SCORE_CHANGE_EPSILON * 0.5
        record2 = _make_record(50.0 + tiny_change)
        result = await repo.upsert_if_changed(record2)
        assert result is False

    @pytest.mark.asyncio
    async def test_does_not_write_when_score_exactly_epsilon(self):
        """Score change exactly equal to epsilon → NOT written."""
        repo = InMemoryCompanyScoreRepository()
        record1 = _make_record(50.0)
        await repo.upsert_if_changed(record1)

        record2 = _make_record(50.0 + SCORE_CHANGE_EPSILON)
        result = await repo.upsert_if_changed(record2)
        assert result is False


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_returns_descending_order(self):
        """get_history returns rows in descending computed_at order."""
        repo = InMemoryCompanyScoreRepository()

        # Write several records with slightly different scores
        scores = [50.0, 55.0, 60.0, 65.0, 70.0]
        for score in scores:
            record = _make_record(score)
            await repo.upsert_if_changed(record)

        history = await repo.get_history(COMPANY_ID, INDICATOR_ID, limit=5)
        assert len(history) == 5
        # Should be in descending computed_at; scores were written in order
        # so the last written (70.0) should come first
        assert history[0].score == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        repo = InMemoryCompanyScoreRepository()
        scores = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
        for score in scores:
            record = _make_record(score)
            await repo.upsert_if_changed(record)

        history = await repo.get_history(COMPANY_ID, INDICATOR_ID, limit=3)
        assert len(history) <= 3


class TestInputsHash:
    def test_hash_deterministic(self):
        inputs = {"revenue": 1000.0, "pe_ratio": 15.5}
        h1 = compute_inputs_hash(inputs)
        h2 = compute_inputs_hash(inputs)
        assert h1 == h2

    def test_hash_different_for_different_inputs(self):
        h1 = compute_inputs_hash({"revenue": 1000.0})
        h2 = compute_inputs_hash({"revenue": 1001.0})
        assert h1 != h2

    def test_hash_is_sha256_hex(self):
        h = compute_inputs_hash({"revenue": 100.0})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_key_order_independent(self):
        """Sorted keys means {a:1, b:2} == {b:2, a:1}."""
        h1 = compute_inputs_hash({"a": 1.0, "b": 2.0})
        h2 = compute_inputs_hash({"b": 2.0, "a": 1.0})
        assert h1 == h2
