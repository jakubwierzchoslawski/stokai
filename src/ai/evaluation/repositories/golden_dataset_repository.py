"""
GoldenDatasetRepository — SQLAlchemy 2.0 async implementation of IGoldenDatasetRepository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.evaluation.interfaces.i_golden_dataset_repository import (
    IGoldenDatasetRepository,
)
from src.ai.evaluation.models.golden_dataset_models import (
    GoldenDatasetItem as GoldenDatasetItemORM,
)
from src.ai.evaluation.schemas.golden_dataset_schemas import (
    GoldenDatasetItem,
    GoldenDatasetItemCreate,
)


class GoldenDatasetRepository(IGoldenDatasetRepository):
    """SQLAlchemy 2.0 async repository for golden_dataset_item rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_item(self, item: GoldenDatasetItemCreate) -> GoldenDatasetItem:
        """INSERT a new golden dataset item with active=False."""
        orm = GoldenDatasetItemORM(
            item_id=uuid4(),
            input=item.input,
            expected_output=item.expected_output,
            quality_metrics=item.quality_metrics,
            source=item.source,
            active=False,
            approved_by=None,
            approved_at=None,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return GoldenDatasetItem.model_validate(orm)

    async def activate_item(
        self, item_id: UUID, approved_by: UUID
    ) -> GoldenDatasetItem:
        """Set active=True, approved_by, approved_at=NOW() on the item."""
        stmt = (
            update(GoldenDatasetItemORM)
            .where(GoldenDatasetItemORM.item_id == item_id)
            .values(
                active=True,
                approved_by=approved_by,
                approved_at=datetime.now(tz=timezone.utc),
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

        # Re-fetch the updated row
        fetch = select(GoldenDatasetItemORM).where(
            GoldenDatasetItemORM.item_id == item_id
        )
        result = await self._session.execute(fetch)
        orm = result.scalar_one()
        return GoldenDatasetItem.model_validate(orm)

    async def list_active(self) -> list[GoldenDatasetItem]:
        """Return all items WHERE active=TRUE."""
        stmt = select(GoldenDatasetItemORM).where(
            GoldenDatasetItemORM.active.is_(True)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [GoldenDatasetItem.model_validate(r) for r in rows]

    async def list_candidates(self) -> list[GoldenDatasetItem]:
        """Return all items WHERE active=FALSE AND approved_at IS NULL."""
        stmt = select(GoldenDatasetItemORM).where(
            GoldenDatasetItemORM.active.is_(False),
            GoldenDatasetItemORM.approved_at.is_(None),
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [GoldenDatasetItem.model_validate(r) for r in rows]

    async def deactivate_item(self, item_id: UUID) -> None:
        """Set active=False on the item."""
        stmt = (
            update(GoldenDatasetItemORM)
            .where(GoldenDatasetItemORM.item_id == item_id)
            .values(active=False)
        )
        await self._session.execute(stmt)
        await self._session.flush()
