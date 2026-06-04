"""
SemanticRepository — SQLAlchemy 2.0 async implementation of ISemanticRepository.

Evidence gate enforced here: commit_fact raises EvidenceGateError when
evidence_count < EVIDENCE_GATE_MIN_COUNT (3).

Cosine similarity queries use pgvector's <=> operator via raw SQL fragment.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.exceptions import EvidenceGateError
from src.ai.memory.interfaces.i_semantic_repository import ISemanticRepository
from src.ai.memory.models.semantic_models import SemanticFact as SemanticFactORM
from src.ai.memory.models.semantic_models import (
    SemanticFactStaging as SemanticFactStagingORM,
)
from src.ai.memory.schemas.semantic_schemas import (
    SemanticFact,
    SemanticFactStaging,
    SemanticFactStagingCreate,
)

EVIDENCE_GATE_MIN_COUNT: int = 3


class SemanticRepository(ISemanticRepository):
    """SQLAlchemy 2.0 async repository for Layer 2 semantic memory."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Staging ───────────────────────────────────────────────────────────────

    async def stage_fact(self, fact: SemanticFactStagingCreate) -> SemanticFactStaging:
        """INSERT a staging row with evidence_count=1."""
        source_ids: list[UUID] = (
            [fact.source_invocation_id] if fact.source_invocation_id else []
        )
        orm = SemanticFactStagingORM(
            staging_id=uuid4(),
            entity_id=fact.entity_id,
            fact_text=fact.fact_text,
            evidence_count=1,
            source_invocation_ids=source_ids,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return SemanticFactStaging.model_validate(orm)

    async def increment_evidence(
        self, staging_id: UUID, source_invocation_id: UUID
    ) -> SemanticFactStaging:
        """Increment evidence_count and append the source invocation UUID."""
        stmt = (
            update(SemanticFactStagingORM)
            .where(SemanticFactStagingORM.staging_id == staging_id)
            .values(
                evidence_count=SemanticFactStagingORM.evidence_count + 1,
                source_invocation_ids=text(
                    "source_invocation_ids || ARRAY[:new_id::uuid]::uuid[]"
                ).bindparams(new_id=str(source_invocation_id)),
            )
            .returning(SemanticFactStagingORM)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one()
        return SemanticFactStaging.model_validate(orm)

    # ── Commit ────────────────────────────────────────────────────────────────

    async def commit_fact(
        self, staging_id: UUID, embedding: list[float]
    ) -> SemanticFact:
        """
        Transfer staging row to semantic_fact when evidence_count >= 3.

        Raises EvidenceGateError if evidence_count < EVIDENCE_GATE_MIN_COUNT.
        """
        result = await self._session.execute(
            select(SemanticFactStagingORM).where(
                SemanticFactStagingORM.staging_id == staging_id
            )
        )
        staging_orm = result.scalar_one()

        if staging_orm.evidence_count < EVIDENCE_GATE_MIN_COUNT:
            raise EvidenceGateError(
                staging_id=staging_id,
                current_count=staging_orm.evidence_count,
                required=EVIDENCE_GATE_MIN_COUNT,
            )

        fact_orm = SemanticFactORM(
            fact_id=uuid4(),
            entity_id=staging_orm.entity_id,
            fact_text=staging_orm.fact_text,
            embedding=embedding,
            evidence_count=staging_orm.evidence_count,
            last_confirmed=datetime.now(tz=timezone.utc),
            source_invocations=staging_orm.source_invocation_ids or [],
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(fact_orm)
        await self._session.flush()

        # Remove staging row
        await self._session.execute(
            delete(SemanticFactStagingORM).where(
                SemanticFactStagingORM.staging_id == staging_id
            )
        )
        await self._session.flush()
        await self._session.refresh(fact_orm)
        return SemanticFact.model_validate(fact_orm)

    # ── Query ─────────────────────────────────────────────────────────────────

    async def query_facts(
        self,
        embedding: list[float],
        limit: int = 20,
        exclude_decayed: bool = True,
    ) -> list[SemanticFact]:
        """
        Return the nearest semantic facts ordered by cosine distance.

        When exclude_decayed=True, omits decayed and retracted facts.
        """
        stmt = select(SemanticFactORM).order_by(
            SemanticFactORM.embedding.op("<=>")(embedding)
        )
        if exclude_decayed:
            stmt = stmt.where(
                SemanticFactORM.decayed_at.is_(None),
                SemanticFactORM.retracted_at.is_(None),
            )
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [SemanticFact.model_validate(r) for r in rows]

    # ── Decay / Retraction ────────────────────────────────────────────────────

    async def mark_decayed(self, fact_ids: list[UUID]) -> int:
        """Bulk-update decayed_at on the supplied fact IDs."""
        if not fact_ids:
            return 0
        stmt = (
            update(SemanticFactORM)
            .where(SemanticFactORM.fact_id.in_(fact_ids))
            .values(decayed_at=datetime.now(tz=timezone.utc))
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def retract_fact(self, fact_id: UUID, retracted_by: UUID) -> None:
        """Set retracted_at and retracted_by on a single fact."""
        stmt = (
            update(SemanticFactORM)
            .where(SemanticFactORM.fact_id == fact_id)
            .values(
                retracted_at=datetime.now(tz=timezone.utc),
                retracted_by=retracted_by,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_unconfirmed_older_than(self, months: int) -> list[SemanticFact]:
        """
        Return facts whose last_confirmed is older than `months` months
        and that have not yet been decayed.
        """
        stmt = (
            select(SemanticFactORM)
            .where(
                SemanticFactORM.last_confirmed
                < text(f"NOW() - INTERVAL '{months} months'"),
                SemanticFactORM.decayed_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [SemanticFact.model_validate(r) for r in rows]
