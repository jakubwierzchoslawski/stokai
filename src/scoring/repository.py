"""ConcreteScoreRepository — append-only score persistence (PLAN-F-003 TASK-009).

Implements the ``ScoreRepository`` Protocol using SQLAlchemy 2 async sessions.

Key invariants:
    - ``append`` only ever INSERTs — no UPDATE, no DELETE (P-08).
    - ``get_latest`` hard-caps returned rows at 50 (REQ-N-005).
    - All queries are tenant-scoped (D3).
    - ``get_stored_hash`` returns None for first-time computations (no prior record).

The session is injected at construction time (DIP); this class has no
knowledge of connection strings or engine configuration.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.scoring import ScoreRecord
from src.scoring.interfaces import ScoreQuery, ScoreResult

_MAX_ROWS = 50


class ConcreteScoreRepository:
    """SQLAlchemy 2 async implementation of the ``ScoreRepository`` Protocol.

    Parameters
    ----------
    session:
        An injected ``AsyncSession``.  The caller owns the transaction
        lifecycle; this class does not commit or roll back.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, result: ScoreResult) -> None:
        """Insert *result* as a new row in ``score_records``.

        Never issues UPDATE or DELETE.

        Raises
        ------
        RuntimeError
            If the database insert fails.
        """
        try:
            record = ScoreRecord(
                score_id=result.score_id,
                tenant_id=result.tenant_id,
                company_id=result.company_id,
                indicator_id=result.indicator_id,
                indicator_version_id=result.indicator_version_id,
                score=result.score,
                geo_weight_applied=result.geo_weight_applied,
                inputs_hash=result.inputs_hash,
                computed_at=result.computed_at,
            )
            self._session.add(record)
            await self._session.flush()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to insert ScoreRecord {result.score_id}: {exc}"
            ) from exc

    async def get_latest(self, query: ScoreQuery) -> list[ScoreResult]:
        """Return the most recent scores matching *query*, capped at 50 rows.

        Filters applied (all optional except tenant_id):
            - tenant_id (required, always applied)
            - company_ids (IN filter when provided)
            - indicator_id (equality filter when provided)
            - computed_at_from / computed_at_to (range filter)

        ORDER BY computed_at DESC, LIMIT min(query.limit, 50).
        """
        limit = min(query.limit, _MAX_ROWS)

        stmt = (
            select(ScoreRecord)
            .where(ScoreRecord.tenant_id == query.tenant_id)
            .order_by(ScoreRecord.computed_at.desc())
            .limit(limit)
        )

        if query.company_ids is not None:
            stmt = stmt.where(ScoreRecord.company_id.in_(query.company_ids))

        if query.indicator_id is not None:
            stmt = stmt.where(ScoreRecord.indicator_id == query.indicator_id)

        if query.computed_at_from is not None:
            stmt = stmt.where(ScoreRecord.computed_at >= query.computed_at_from)

        if query.computed_at_to is not None:
            stmt = stmt.where(ScoreRecord.computed_at <= query.computed_at_to)

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        return [self._to_score_result(row) for row in rows]

    async def get_stored_hash(
        self,
        company_id: uuid.UUID,
        indicator_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> str | None:
        """Return the most recently stored ``inputs_hash`` for the given triple.

        Returns ``None`` when no prior record exists (first-time computation).
        """
        stmt = (
            select(ScoreRecord.inputs_hash)
            .where(
                ScoreRecord.tenant_id == tenant_id,
                ScoreRecord.company_id == company_id,
                ScoreRecord.indicator_id == indicator_id,
            )
            .order_by(ScoreRecord.computed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    @staticmethod
    def _to_score_result(record: ScoreRecord) -> ScoreResult:
        """Convert an ORM ``ScoreRecord`` to a ``ScoreResult`` Pydantic model."""
        return ScoreResult(
            score_id=record.score_id,
            company_id=record.company_id,
            indicator_id=record.indicator_id,
            indicator_version_id=record.indicator_version_id,
            score=record.score,
            geo_weight_applied=record.geo_weight_applied,
            inputs_hash=record.inputs_hash,
            computed_at=record.computed_at,
            tenant_id=record.tenant_id,
        )
