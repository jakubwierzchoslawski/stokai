"""
IGoldenDatasetRepository — abstract interface for golden_dataset_item persistence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.ai.evaluation.schemas.golden_dataset_schemas import (
    GoldenDatasetItem,
    GoldenDatasetItemCreate,
)


class IGoldenDatasetRepository(ABC):
    """Abstract repository for golden dataset items used by Tier-2 regression."""

    @abstractmethod
    async def create_item(self, item: GoldenDatasetItemCreate) -> GoldenDatasetItem:
        """Insert a new golden dataset item with active=False."""
        ...

    @abstractmethod
    async def activate_item(
        self, item_id: UUID, approved_by: UUID
    ) -> GoldenDatasetItem:
        """Set active=True, approved_by, and approved_at=NOW() on the item."""
        ...

    @abstractmethod
    async def list_active(self) -> list[GoldenDatasetItem]:
        """Return all items WHERE active=TRUE."""
        ...

    @abstractmethod
    async def list_candidates(self) -> list[GoldenDatasetItem]:
        """Return all items WHERE active=FALSE AND approved_at IS NULL."""
        ...

    @abstractmethod
    async def deactivate_item(self, item_id: UUID) -> None:
        """Set active=False on the item."""
        ...
