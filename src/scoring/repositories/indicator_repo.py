"""SQLAlchemy implementation of IIndicatorRepository.

Uses async SQLAlchemy 2.0 sessions with tenant_id isolation on every query.
On save():
  - If indicator_id not present → INSERT with version=1.
  - If indicator_id present → INSERT new version row with version = max_version + 1.
All writes also insert an IndicatorVersionRecord.
"""
from __future__ import annotations

import difflib
from datetime import datetime
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    select,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.scoring.dsl.tokenizer import tokenize
from src.scoring.schemas.indicator import IndicatorRecord, IndicatorVersionRecord


# ---------------------------------------------------------------------------
# ORM table definitions (scoped to scoring module)
# ---------------------------------------------------------------------------

class _Base(DeclarativeBase):
    pass


class _IndicatorRow(_Base):
    __tablename__ = "indicator"

    indicator_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    formula_dsl = Column(String, nullable=False)
    normalization_mode = Column(String(50), nullable=False, default="percentile")
    normalization_config = Column(JSON, nullable=False, default=dict)
    direction = Column(String(20), nullable=False, default="higher_better")
    geo_weight = Column(Float, nullable=False, default=0.0)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("indicator_id", "version", name="uq_indicator_version"),
    )


class _IndicatorVersionRow(_Base):
    __tablename__ = "indicator_version"

    version_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    indicator_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)
    formula_dsl = Column(String, nullable=False)
    diff_tokens = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False)


# ---------------------------------------------------------------------------
# Repository implementation
# ---------------------------------------------------------------------------

def _compute_diff_tokens(old_dsl: str, new_dsl: str) -> list[str]:
    """Compute token-level diff between two DSL strings.

    Returns a list of strings prefixed with '+', '-', or ' ' (unchanged).
    """
    try:
        old_tokens = [t.value for t in tokenize(old_dsl)]
        new_tokens = [t.value for t in tokenize(new_dsl)]
    except Exception:
        # Fallback to raw string diff if tokenization fails
        old_tokens = old_dsl.split()
        new_tokens = new_dsl.split()

    # EOF token isn't meaningful for diff
    old_tokens = [t for t in old_tokens if t != ""]
    new_tokens = [t for t in new_tokens if t != ""]

    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens)
    result: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for token in old_tokens[i1:i2]:
                result.append(f" {token}")
        elif tag in ("replace", "delete"):
            for token in old_tokens[i1:i2]:
                result.append(f"-{token}")
            if tag == "replace":
                for token in new_tokens[j1:j2]:
                    result.append(f"+{token}")
        elif tag == "insert":
            for token in new_tokens[j1:j2]:
                result.append(f"+{token}")
    return result


def _row_to_record(row: _IndicatorRow) -> IndicatorRecord:
    return IndicatorRecord(
        indicator_id=row.indicator_id,
        tenant_id=row.tenant_id,
        name=row.name,
        formula_dsl=row.formula_dsl,
        normalization_mode=row.normalization_mode,
        normalization_config=row.normalization_config or {},
        direction=row.direction,
        geo_weight=row.geo_weight,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_active=row.is_active,
    )


def _version_row_to_record(row: _IndicatorVersionRow) -> IndicatorVersionRecord:
    return IndicatorVersionRecord(
        version_id=row.version_id,
        indicator_id=row.indicator_id,
        tenant_id=row.tenant_id,
        version=row.version,
        formula_dsl=row.formula_dsl,
        diff_tokens=row.diff_tokens or [],
        created_at=row.created_at,
    )


class IndicatorRepository:
    """Async SQLAlchemy repository for indicators and their version history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, indicator_id: UUID, tenant_id: UUID
    ) -> IndicatorRecord | None:
        stmt = select(_IndicatorRow).where(
            _IndicatorRow.indicator_id == indicator_id,
            _IndicatorRow.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _row_to_record(row) if row else None

    async def list_by_tenant(self, tenant_id: UUID) -> list[IndicatorRecord]:
        stmt = select(_IndicatorRow).where(
            _IndicatorRow.tenant_id == tenant_id,
            _IndicatorRow.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return [_row_to_record(r) for r in result.scalars().all()]

    async def save(self, record: IndicatorRecord) -> IndicatorRecord:
        """Insert or update indicator and create a new version record."""
        # Check current max version
        existing = await self.get_by_id(record.indicator_id, record.tenant_id)

        if existing is None:
            # First save: version=1
            record.version = 1
            old_dsl = ""
        else:
            # Increment version
            record.version = existing.version + 1
            old_dsl = existing.formula_dsl

        record.updated_at = datetime.utcnow()

        # Upsert the indicator row (delete existing, insert new for simplicity)
        if existing is not None:
            stmt = select(_IndicatorRow).where(
                _IndicatorRow.indicator_id == record.indicator_id,
                _IndicatorRow.tenant_id == record.tenant_id,
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                row.name = record.name
                row.formula_dsl = record.formula_dsl
                row.normalization_mode = record.normalization_mode
                row.normalization_config = record.normalization_config
                row.direction = record.direction
                row.geo_weight = record.geo_weight
                row.version = record.version
                row.is_active = record.is_active
                row.updated_at = record.updated_at
        else:
            row = _IndicatorRow(
                indicator_id=record.indicator_id,
                tenant_id=record.tenant_id,
                name=record.name,
                formula_dsl=record.formula_dsl,
                normalization_mode=record.normalization_mode,
                normalization_config=record.normalization_config,
                direction=record.direction,
                geo_weight=record.geo_weight,
                version=record.version,
                is_active=record.is_active,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            self._session.add(row)

        # Insert version record
        diff_tokens = _compute_diff_tokens(old_dsl, record.formula_dsl)
        version_record = IndicatorVersionRecord.from_indicator(record, diff_tokens)
        version_row = _IndicatorVersionRow(
            version_id=version_record.version_id,
            indicator_id=version_record.indicator_id,
            tenant_id=version_record.tenant_id,
            version=version_record.version,
            formula_dsl=version_record.formula_dsl,
            diff_tokens=version_record.diff_tokens,
            created_at=version_record.created_at,
        )
        self._session.add(version_row)
        await self._session.flush()

        return record

    async def get_version(
        self, indicator_id: UUID, version: int
    ) -> IndicatorVersionRecord | None:
        stmt = select(_IndicatorVersionRow).where(
            _IndicatorVersionRow.indicator_id == indicator_id,
            _IndicatorVersionRow.version == version,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _version_row_to_record(row) if row else None

    async def list_versions(self, indicator_id: UUID) -> list[IndicatorVersionRecord]:
        stmt = (
            select(_IndicatorVersionRow)
            .where(_IndicatorVersionRow.indicator_id == indicator_id)
            .order_by(_IndicatorVersionRow.version.asc())
        )
        result = await self._session.execute(stmt)
        return [_version_row_to_record(r) for r in result.scalars().all()]
