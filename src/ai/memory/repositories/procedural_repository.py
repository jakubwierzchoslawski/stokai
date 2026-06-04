"""
ProceduralRepository — SQLAlchemy 2.0 async implementation of IProceduralRepository.

get_patterns: filters by context_tags overlap (GIN), returns only approved, non-retracted.
list_pending_approval: returns patterns with approved_at IS NULL AND retracted_at IS NULL.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.interfaces.i_procedural_repository import IProceduralRepository
from src.ai.memory.models.procedural_models import ProceduralPattern as ProceduralPatternORM
from src.ai.memory.schemas.procedural_schemas import (
    ProceduralPattern,
    ProceduralPatternCreate,
)


class ProceduralRepository(IProceduralRepository):
    """SQLAlchemy 2.0 async repository for Layer 3 procedural patterns."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_patterns(
        self,
        context_tags: list[str],
        agent_role: str | None = None,
    ) -> list[ProceduralPattern]:
        """
        Return approved, non-retracted patterns whose context_tags overlap
        the supplied tags.  Optionally filtered by agent_role presence in
        recommended_for_agents.
        """
        stmt = select(ProceduralPatternORM).where(
            ProceduralPatternORM.approved_at.isnot(None),
            ProceduralPatternORM.retracted_at.is_(None),
        )
        if context_tags:
            # PostgreSQL GIN overlap operator: context_tags && ARRAY[...]
            stmt = stmt.where(
                ProceduralPatternORM.context_tags.overlap(context_tags)
            )
        if agent_role is not None:
            stmt = stmt.where(
                ProceduralPatternORM.recommended_for_agents.any(agent_role)
            )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [ProceduralPattern.model_validate(r) for r in rows]

    async def create_pattern(
        self, pattern: ProceduralPatternCreate
    ) -> ProceduralPattern:
        """INSERT a new pattern row."""
        orm = ProceduralPatternORM(
            pattern_id=uuid4(),
            pattern_type=pattern.pattern_type,
            context_tags=pattern.context_tags,
            pattern_text=pattern.pattern_text,
            authored_by=pattern.authored_by,
            approved_at=None,
            approved_by=None,
            version=pattern.version,
            success_rate=pattern.success_rate,
            sample_size=pattern.sample_size,
            confidence=pattern.confidence,
            recommended_for_agents=pattern.recommended_for_agents,
            created_at=datetime.now(tz=timezone.utc),
            retracted_at=None,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return ProceduralPattern.model_validate(orm)

    async def approve_pattern(
        self, pattern_id: UUID, approved_by: UUID
    ) -> ProceduralPattern:
        """Set approved_at=NOW() and approved_by."""
        stmt = (
            update(ProceduralPatternORM)
            .where(ProceduralPatternORM.pattern_id == pattern_id)
            .values(
                approved_at=datetime.now(tz=timezone.utc),
                approved_by=approved_by,
            )
            .returning(ProceduralPatternORM)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one()
        await self._session.flush()
        return ProceduralPattern.model_validate(orm)

    async def retract_pattern(self, pattern_id: UUID, retracted_by: UUID) -> None:
        """Set retracted_at=NOW()."""
        stmt = (
            update(ProceduralPatternORM)
            .where(ProceduralPatternORM.pattern_id == pattern_id)
            .values(retracted_at=datetime.now(tz=timezone.utc))
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_pending_approval(self) -> list[ProceduralPattern]:
        """Return unapproved, non-retracted patterns."""
        stmt = select(ProceduralPatternORM).where(
            ProceduralPatternORM.approved_at.is_(None),
            ProceduralPatternORM.retracted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [ProceduralPattern.model_validate(r) for r in rows]
