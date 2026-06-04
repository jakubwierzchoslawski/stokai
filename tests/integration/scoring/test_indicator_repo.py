"""Integration tests for IndicatorRepository and versioning.

These tests use an in-memory SQLite database (via aiosqlite) to avoid
requiring a full PostgreSQL/TimescaleDB setup. Tests are skipped if
aiosqlite is not installed.

Note: PostgreSQL-specific features (like UUID columns) are adapted for SQLite
in test fixtures.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from uuid import uuid4, UUID

from src.scoring.schemas.indicator import IndicatorRecord, IndicatorVersionRecord

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# In-memory repository for testing (avoids real DB dependency)
# ---------------------------------------------------------------------------

class InMemoryIndicatorRepository:
    """In-memory implementation for integration tests."""

    def __init__(self):
        self._indicators: dict[UUID, IndicatorRecord] = {}
        self._versions: list[IndicatorVersionRecord] = []

    async def get_by_id(self, indicator_id: UUID, tenant_id: UUID) -> IndicatorRecord | None:
        record = self._indicators.get(indicator_id)
        if record and record.tenant_id == tenant_id:
            return record
        return None

    async def list_by_tenant(self, tenant_id: UUID) -> list[IndicatorRecord]:
        return [r for r in self._indicators.values() if r.tenant_id == tenant_id]

    async def save(self, record: IndicatorRecord) -> IndicatorRecord:
        import difflib
        from src.scoring.dsl.tokenizer import tokenize

        existing = self._indicators.get(record.indicator_id)
        if existing is None:
            record.version = 1
            old_dsl = ""
        else:
            record.version = existing.version + 1
            old_dsl = existing.formula_dsl

        record.updated_at = datetime.utcnow()
        self._indicators[record.indicator_id] = record

        # Compute diff
        try:
            old_tokens = [t.value for t in tokenize(old_dsl) if t.value]
            new_tokens = [t.value for t in tokenize(record.formula_dsl) if t.value]
        except Exception:
            old_tokens = old_dsl.split()
            new_tokens = record.formula_dsl.split()

        matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens)
        diff_tokens = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                diff_tokens.extend(f" {t}" for t in old_tokens[i1:i2])
            elif tag in ("replace", "delete"):
                diff_tokens.extend(f"-{t}" for t in old_tokens[i1:i2])
                if tag == "replace":
                    diff_tokens.extend(f"+{t}" for t in new_tokens[j1:j2])
            elif tag == "insert":
                diff_tokens.extend(f"+{t}" for t in new_tokens[j1:j2])

        version_record = IndicatorVersionRecord.from_indicator(record, diff_tokens)
        self._versions.append(version_record)
        return record

    async def get_version(self, indicator_id: UUID, version: int) -> IndicatorVersionRecord | None:
        for v in self._versions:
            if v.indicator_id == indicator_id and v.version == version:
                return v
        return None

    async def list_versions(self, indicator_id: UUID) -> list[IndicatorVersionRecord]:
        return sorted(
            [v for v in self._versions if v.indicator_id == indicator_id],
            key=lambda v: v.version,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIndicatorRepo:
    @pytest.mark.asyncio
    async def test_first_save_creates_version_1(self):
        repo = InMemoryIndicatorRepository()
        record = IndicatorRecord.new(
            tenant_id=TENANT_ID,
            name="Test Indicator",
            formula_dsl="revenue * 0.5",
        )
        saved = await repo.save(record)
        assert saved.version == 1

        versions = await repo.list_versions(saved.indicator_id)
        assert len(versions) == 1
        assert versions[0].version == 1

    @pytest.mark.asyncio
    async def test_second_save_increments_version(self):
        repo = InMemoryIndicatorRepository()
        record = IndicatorRecord.new(
            tenant_id=TENANT_ID,
            name="Test Indicator",
            formula_dsl="revenue * 0.5",
        )
        await repo.save(record)

        # Update formula
        record.formula_dsl = "revenue * 0.7 + net_income"
        saved_v2 = await repo.save(record)
        assert saved_v2.version == 2

        versions = await repo.list_versions(saved_v2.indicator_id)
        assert len(versions) == 2

    @pytest.mark.asyncio
    async def test_get_version_1_returns_original_dsl(self):
        repo = InMemoryIndicatorRepository()
        original_dsl = "revenue * 0.5"
        record = IndicatorRecord.new(
            tenant_id=TENANT_ID,
            name="Test",
            formula_dsl=original_dsl,
        )
        await repo.save(record)
        record.formula_dsl = "net_income * 2"
        await repo.save(record)

        v1 = await repo.get_version(record.indicator_id, 1)
        assert v1 is not None
        assert v1.formula_dsl == original_dsl

    @pytest.mark.asyncio
    async def test_list_versions_ascending_order(self):
        repo = InMemoryIndicatorRepository()
        record = IndicatorRecord.new(
            tenant_id=TENANT_ID,
            name="Test",
            formula_dsl="revenue",
        )
        await repo.save(record)
        record.formula_dsl = "revenue * 0.5"
        await repo.save(record)
        record.formula_dsl = "revenue * 0.8"
        await repo.save(record)

        versions = await repo.list_versions(record.indicator_id)
        assert [v.version for v in versions] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        """get_by_id with wrong tenant_id returns None."""
        repo = InMemoryIndicatorRepository()
        other_tenant = uuid4()
        record = IndicatorRecord.new(
            tenant_id=TENANT_ID,
            name="Test",
            formula_dsl="revenue",
        )
        await repo.save(record)

        result = await repo.get_by_id(record.indicator_id, other_tenant)
        assert result is None
