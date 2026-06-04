"""SQLAlchemy implementation of IScoringProfileRepository."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.scoring.schemas.scoring_profile import ProfileIndicatorWeight, ScoringProfileRecord


class _Base(DeclarativeBase):
    pass


class _ScoringProfileRow(_Base):
    __tablename__ = "scoring_profile"

    profile_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    # indicators stored as [{indicator_id, weight}, ...]
    indicators = Column(JSON, nullable=False, default=list)
    is_builtin = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


def _row_to_record(row: _ScoringProfileRow) -> ScoringProfileRecord:
    indicators = [
        ProfileIndicatorWeight(
            indicator_id=UUID(item["indicator_id"]),
            weight=item["weight"],
        )
        for item in (row.indicators or [])
    ]
    return ScoringProfileRecord(
        profile_id=row.profile_id,
        tenant_id=row.tenant_id,
        name=row.name,
        indicators=indicators,
        is_builtin=row.is_builtin,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ScoringProfileRepository:
    """Async SQLAlchemy repository for scoring profiles."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, profile_id: UUID, tenant_id: UUID
    ) -> ScoringProfileRecord | None:
        stmt = select(_ScoringProfileRow).where(
            _ScoringProfileRow.profile_id == profile_id,
            _ScoringProfileRow.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _row_to_record(row) if row else None

    async def list_by_tenant(self, tenant_id: UUID) -> list[ScoringProfileRecord]:
        stmt = select(_ScoringProfileRow).where(
            _ScoringProfileRow.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        return [_row_to_record(r) for r in result.scalars().all()]

    async def save(self, record: ScoringProfileRecord) -> ScoringProfileRecord:
        existing_stmt = select(_ScoringProfileRow).where(
            _ScoringProfileRow.profile_id == record.profile_id,
        )
        result = await self._session.execute(existing_stmt)
        row = result.scalar_one_or_none()

        indicators_json = [
            {"indicator_id": str(iw.indicator_id), "weight": iw.weight}
            for iw in record.indicators
        ]

        if row is None:
            row = _ScoringProfileRow(
                profile_id=record.profile_id,
                tenant_id=record.tenant_id,
                name=record.name,
                indicators=indicators_json,
                is_builtin=record.is_builtin,
                version=record.version,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            self._session.add(row)
        else:
            row.name = record.name
            row.indicators = indicators_json
            row.version = record.version
            row.updated_at = datetime.utcnow()

        await self._session.flush()
        return record
