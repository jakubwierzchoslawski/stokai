"""
GoldenDatasetService — application service for managing the golden dataset.

Provides higher-level operations over IGoldenDatasetRepository:
  - create_candidate: insert new item with active=False
  - approve_candidate: activate item with approver info
  - list_candidates: items awaiting approval
  - list_active: production-ready items
  - deactivate: remove item from active regression suite
"""
from __future__ import annotations

import logging
from uuid import UUID

from src.ai.evaluation.interfaces.i_golden_dataset_repository import (
    IGoldenDatasetRepository,
)
from src.ai.evaluation.schemas.golden_dataset_schemas import (
    GoldenDatasetItem,
    GoldenDatasetItemCreate,
)

logger = logging.getLogger(__name__)


class GoldenDatasetService:
    """
    Application service for golden dataset lifecycle management.

    Parameters
    ----------
    golden_dataset_repo:
        IGoldenDatasetRepository implementation.
    """

    def __init__(self, golden_dataset_repo: IGoldenDatasetRepository) -> None:
        self._repo = golden_dataset_repo

    async def create_candidate(
        self, item: GoldenDatasetItemCreate
    ) -> GoldenDatasetItem:
        """
        Insert a new golden dataset item as an inactive candidate.

        Candidates are always inserted with active=False and must be
        explicitly approved by an admin before entering the regression suite.
        """
        result = await self._repo.create_item(item)
        logger.debug(
            "GoldenDatasetService: created candidate item_id=%s source=%s",
            result.item_id,
            result.source,
        )
        return result

    async def approve_candidate(
        self, item_id: UUID, approved_by: UUID
    ) -> GoldenDatasetItem:
        """
        Activate a candidate item and record the approver.

        Sets active=True, approved_by=approved_by, approved_at=NOW().
        """
        result = await self._repo.activate_item(item_id, approved_by)
        logger.debug(
            "GoldenDatasetService: approved item_id=%s by approver=%s",
            item_id,
            approved_by,
        )
        return result

    async def list_candidates(self) -> list[GoldenDatasetItem]:
        """Return all items awaiting approval (active=False, approved_at IS NULL)."""
        return await self._repo.list_candidates()

    async def list_active(self) -> list[GoldenDatasetItem]:
        """Return all items in the active regression suite (active=TRUE)."""
        return await self._repo.list_active()

    async def deactivate(self, item_id: UUID) -> None:
        """Remove an item from the active regression suite (active=False)."""
        await self._repo.deactivate_item(item_id)
        logger.debug(
            "GoldenDatasetService: deactivated item_id=%s",
            item_id,
        )
