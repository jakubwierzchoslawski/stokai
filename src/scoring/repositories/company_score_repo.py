"""Company score repository with D4 snapshot-write guard.

D4 rule: write a new row ONLY when the score differs from the last stored value
by more than SCORE_CHANGE_EPSILON (0.001).

inputs_hash = SHA-256 of canonical JSON (sorted keys, fixed float precision 6dp).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, Float, String, desc, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.scoring.schemas.company_score import CompanyScoreRecord

logger = logging.getLogger(__name__)

SCORE_CHANGE_EPSILON = 0.001


# ---------------------------------------------------------------------------
# ORM table
# ---------------------------------------------------------------------------

class _Base(DeclarativeBase):
    pass


class _CompanyScoreRow(_Base):
    __tablename__ = "company_score"

    score_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    company_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    indicator_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    raw_value = Column(Float, nullable=True)
    score = Column(Float, nullable=False)
    percentile = Column(Float, nullable=True)
    geo_adjusted = Column(Float, nullable=True)
    inputs_hash = Column(String(64), nullable=False)
    computed_at = Column(DateTime, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------

def compute_inputs_hash(inputs: dict) -> str:
    """Compute SHA-256 hash of *inputs* in canonical form.

    Canonical form: JSON with sorted keys, floats rounded to 6 decimal places.
    """
    def _canonicalize(obj):
        if isinstance(obj, float):
            return round(obj, 6)
        if isinstance(obj, dict):
            return {k: _canonicalize(v) for k, v in sorted(obj.items())}
        if isinstance(obj, (list, tuple)):
            return [_canonicalize(v) for v in obj]
        return obj

    canonical = _canonicalize(inputs)
    serialized = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

def _row_to_record(row: _CompanyScoreRow) -> CompanyScoreRecord:
    return CompanyScoreRecord(
        score_id=row.score_id,
        company_id=row.company_id,
        indicator_id=row.indicator_id,
        tenant_id=row.tenant_id,
        raw_value=row.raw_value,
        score=row.score,
        percentile=row.percentile,
        geo_adjusted=row.geo_adjusted,
        inputs_hash=row.inputs_hash,
        computed_at=row.computed_at,
    )


class CompanyScoreRepository:
    """Async SQLAlchemy repository for company scores.

    Enforces D4: rows written only when score changes by > SCORE_CHANGE_EPSILON.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current(
        self, company_id: UUID, indicator_id: UUID
    ) -> CompanyScoreRecord | None:
        stmt = (
            select(_CompanyScoreRow)
            .where(
                _CompanyScoreRow.company_id == company_id,
                _CompanyScoreRow.indicator_id == indicator_id,
            )
            .order_by(desc(_CompanyScoreRow.computed_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _row_to_record(row) if row else None

    async def upsert_if_changed(self, record: CompanyScoreRecord) -> bool:
        """Write *record* only if score differs from current by > SCORE_CHANGE_EPSILON.

        Returns:
            True if a new row was written; False if score is unchanged.
        """
        current = await self.get_current(record.company_id, record.indicator_id)

        if current is not None:
            score_diff = abs(record.score - current.score)
            if score_diff <= SCORE_CHANGE_EPSILON:
                logger.debug(
                    "Score unchanged (diff=%.6f <= epsilon=%.3f) for company=%s indicator=%s — skipping write.",
                    score_diff,
                    SCORE_CHANGE_EPSILON,
                    record.company_id,
                    record.indicator_id,
                )
                return False

        row = _CompanyScoreRow(
            score_id=record.score_id,
            company_id=record.company_id,
            indicator_id=record.indicator_id,
            tenant_id=record.tenant_id,
            raw_value=record.raw_value,
            score=record.score,
            percentile=record.percentile,
            geo_adjusted=record.geo_adjusted,
            inputs_hash=record.inputs_hash,
            computed_at=record.computed_at,
        )
        self._session.add(row)
        await self._session.flush()
        return True

    async def get_history(
        self, company_id: UUID, indicator_id: UUID, limit: int = 90
    ) -> list[CompanyScoreRecord]:
        stmt = (
            select(_CompanyScoreRow)
            .where(
                _CompanyScoreRow.company_id == company_id,
                _CompanyScoreRow.indicator_id == indicator_id,
            )
            .order_by(desc(_CompanyScoreRow.computed_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_row_to_record(r) for r in result.scalars().all()]
