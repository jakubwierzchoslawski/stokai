"""Company score repository with D4 snapshot-write guard.

D4 rule: write a new row ONLY when the score differs from the last stored value
by more than SCORE_CHANGE_EPSILON (0.001).

inputs_hash = SHA-256 of canonical JSON (sorted keys, fixed float precision 6dp).

PLAN-F-018 TASK-003: Added bulk_update_geo_adjusted for targeted geo-modifier writes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Float, String, desc, select, text
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

    async def bulk_update_geo_adjusted(
        self,
        updates: list,  # list[GeoAdjustedUpdate] — imported lazily to avoid circular import
    ) -> int:
        """Write geo_adjusted values for multiple (company_id, indicator_id) pairs.

        Inserts a new company_score row for each update (D4 event-driven snapshot),
        carrying the existing score/raw_value/percentile/inputs_hash from the most
        recent row but with the new geo_adjusted value and fresh computed_at.

        Groups updates by indicator_id — one SELECT + one INSERT batch per indicator.
        O(indicators) DB round-trips (no N+1).

        Applies epsilon guard: skips pairs where
        abs(new_geo_adjusted - current_geo_adjusted) <= SCORE_CHANGE_EPSILON.

        Returns:
            Count of rows actually inserted.
        """
        if not updates:
            return 0

        # Group updates by indicator_id
        by_indicator: dict = defaultdict(list)
        for upd in updates:
            by_indicator[upd.indicator_id].append(upd)

        total_inserted = 0

        for indicator_id, indicator_updates in by_indicator.items():
            company_ids = [str(upd.company_id) for upd in indicator_updates]

            # Single SELECT for all companies in this indicator group
            # Fetches the most-recent row for each company
            select_stmt = text(
                """
                SELECT DISTINCT ON (company_id)
                    score_id, company_id, indicator_id, tenant_id,
                    raw_value, score, percentile, geo_adjusted, inputs_hash, computed_at
                FROM company_score
                WHERE company_id = ANY(:company_ids)
                  AND indicator_id = :indicator_id
                ORDER BY company_id, computed_at DESC
                """
            )
            result = await self._session.execute(
                select_stmt,
                {
                    "company_ids": company_ids,
                    "indicator_id": str(indicator_id),
                },
            )
            rows = result.fetchall()

            # Build a lookup: company_id → current row
            current_by_company: dict = {row.company_id: row for row in rows}

            # Build INSERT params
            insert_params: list[dict] = []
            for upd in indicator_updates:
                current = current_by_company.get(upd.company_id)
                if current is None:
                    logger.warning(
                        "bulk_update_geo_adjusted: no existing company_score row for "
                        "company=%s indicator=%s — skipping.",
                        upd.company_id,
                        upd.indicator_id,
                    )
                    continue

                current_geo = current.geo_adjusted
                if current_geo is None:
                    current_geo = 0.0

                diff = abs(upd.geo_adjusted - current_geo)
                if diff <= SCORE_CHANGE_EPSILON:
                    logger.debug(
                        "bulk_update_geo_adjusted: geo_adjusted unchanged "
                        "(diff=%.6f <= epsilon=%.3f) for company=%s indicator=%s — skipping.",
                        diff,
                        SCORE_CHANGE_EPSILON,
                        upd.company_id,
                        upd.indicator_id,
                    )
                    continue

                insert_params.append(
                    {
                        "score_id": str(uuid4()),
                        "company_id": str(upd.company_id),
                        "indicator_id": str(upd.indicator_id),
                        "tenant_id": str(current.tenant_id),
                        "raw_value": current.raw_value,
                        "score": current.score,
                        "percentile": current.percentile,
                        "geo_adjusted": upd.geo_adjusted,
                        "inputs_hash": current.inputs_hash,
                        "computed_at": upd.computed_at,
                    }
                )

            if insert_params:
                insert_stmt = text(
                    """
                    INSERT INTO company_score (
                        score_id, company_id, indicator_id, tenant_id,
                        raw_value, score, percentile, geo_adjusted,
                        inputs_hash, computed_at
                    ) VALUES (
                        :score_id, :company_id, :indicator_id, :tenant_id,
                        :raw_value, :score, :percentile, :geo_adjusted,
                        :inputs_hash, :computed_at
                    )
                    """
                )
                await self._session.execute(insert_stmt, insert_params)
                await self._session.flush()
                total_inserted += len(insert_params)

        return total_inserted
