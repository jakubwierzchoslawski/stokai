"""
Unit tests for TASK-008: GoldenDatasetService.

TDD: written before the implementation exists.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.evaluation.schemas.golden_dataset_schemas import (
    GoldenDatasetItem,
    GoldenDatasetItemCreate,
)


def _make_item_create() -> GoldenDatasetItemCreate:
    return GoldenDatasetItemCreate(
        input={"query": "Analyse AAPL"},
        expected_output={"signal": "BUY"},
        quality_metrics={"factual_grounding": 0.9},
        source="hand_authored",
    )


def _make_item(active: bool = False, approved_at=None) -> GoldenDatasetItem:
    return GoldenDatasetItem(
        item_id=uuid.uuid4(),
        input={"query": "Analyse AAPL"},
        expected_output={"signal": "BUY"},
        quality_metrics={"factual_grounding": 0.9},
        source="hand_authored",
        active=active,
        approved_at=approved_at,
        created_at=datetime.now(tz=timezone.utc),
    )


# ── create_candidate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_dataset_service_create_candidate_inactive():
    """create_candidate should always insert item with active=False."""
    from src.ai.evaluation.services.golden_dataset_service import GoldenDatasetService

    mock_repo = AsyncMock()
    inactive_item = _make_item(active=False)
    mock_repo.create_item = AsyncMock(return_value=inactive_item)

    service = GoldenDatasetService(golden_dataset_repo=mock_repo)
    result = await service.create_candidate(_make_item_create())

    assert result.active is False
    mock_repo.create_item.assert_called_once()


# ── approve_candidate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_dataset_service_approve_candidate_activates():
    """approve_candidate should call activate_item and return active item."""
    from src.ai.evaluation.services.golden_dataset_service import GoldenDatasetService

    mock_repo = AsyncMock()
    item_id = uuid.uuid4()
    approver_id = uuid.uuid4()
    active_item = _make_item(active=True, approved_at=datetime.now(tz=timezone.utc))
    active_item = active_item.model_copy(
        update={"approved_by": approver_id, "active": True}
    )
    mock_repo.activate_item = AsyncMock(return_value=active_item)

    service = GoldenDatasetService(golden_dataset_repo=mock_repo)
    result = await service.approve_candidate(item_id=item_id, approved_by=approver_id)

    assert result.active is True
    mock_repo.activate_item.assert_called_once_with(item_id, approver_id)


# ── list_candidates ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_dataset_service_list_candidates():
    """list_candidates should return items with active=False and no approved_at."""
    from src.ai.evaluation.services.golden_dataset_service import GoldenDatasetService

    mock_repo = AsyncMock()
    candidates = [_make_item(active=False) for _ in range(3)]
    mock_repo.list_candidates = AsyncMock(return_value=candidates)

    service = GoldenDatasetService(golden_dataset_repo=mock_repo)
    result = await service.list_candidates()

    assert len(result) == 3
    assert all(not item.active for item in result)


# ── list_active ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_dataset_service_list_active():
    """list_active should return only active items."""
    from src.ai.evaluation.services.golden_dataset_service import GoldenDatasetService

    mock_repo = AsyncMock()
    active_items = [
        _make_item(active=True, approved_at=datetime.now(tz=timezone.utc))
        for _ in range(5)
    ]
    mock_repo.list_active = AsyncMock(return_value=active_items)

    service = GoldenDatasetService(golden_dataset_repo=mock_repo)
    result = await service.list_active()

    assert len(result) == 5


# ── deactivate ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_golden_dataset_service_deactivate():
    """deactivate should call repo.deactivate_item."""
    from src.ai.evaluation.services.golden_dataset_service import GoldenDatasetService

    mock_repo = AsyncMock()
    mock_repo.deactivate_item = AsyncMock(return_value=None)

    item_id = uuid.uuid4()
    service = GoldenDatasetService(golden_dataset_repo=mock_repo)
    await service.deactivate(item_id=item_id)

    mock_repo.deactivate_item.assert_called_once_with(item_id)
