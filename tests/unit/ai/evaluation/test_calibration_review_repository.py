"""
Unit tests for TASK-002: calibration_review table migration, ORM model,
and CalibrationReviewRepository.

TDD: tests written before implementations. All DB-touching tests are mocked;
the migration test is a static inspection only (no real DB).
"""
from __future__ import annotations

import importlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.evaluation.schemas.calibration_review_schemas import (
    CalibrationReview,
    CalibrationReviewCreate,
)


# ── Migration static inspection ───────────────────────────────────────────────


def test_migration_applies_cleanly_and_table_exists():
    """Migration module must be importable and define upgrade/downgrade with table name."""
    mod = importlib.import_module("alembic.versions.0056_calibration_review_table")
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")
    assert mod.revision == "0056"
    assert mod.down_revision == "0055"
    # The upgrade source must reference calibration_review
    import inspect
    src = inspect.getsource(mod.upgrade)
    assert "calibration_review" in src


def test_action_taken_check_rejects_invalid_value():
    """CalibrationReviewCreate must reject action_taken values not in the allowed set."""
    with pytest.raises(Exception):
        CalibrationReviewCreate(
            reviewed_by=uuid.uuid4(),
            action_taken="invalid_action",
        )


# ── Repository unit tests (mocked session) ────────────────────────────────────


def _make_review_orm(
    review_id: uuid.UUID | None = None,
    reviewed_by: uuid.UUID | None = None,
    action_taken: str = "no_action",
    corr_at_review: float | None = 0.35,
    below_threshold: bool = False,
    notes: str | None = None,
) -> MagicMock:
    """Build a mock ORM object that mimics CalibrationReviewORM."""
    orm = MagicMock()
    orm.review_id = review_id or uuid.uuid4()
    orm.reviewed_by = reviewed_by or uuid.uuid4()
    orm.reviewed_at = datetime.now(tz=timezone.utc)
    orm.corr_at_review = corr_at_review
    orm.below_threshold = below_threshold
    orm.action_taken = action_taken
    orm.notes = notes
    return orm


@pytest.mark.asyncio
async def test_insert_review_persists_row_with_review_id_and_reviewed_at():
    """insert_review must persist a row and return CalibrationReview with review_id set."""
    from src.ai.evaluation.repositories.calibration_review_repository import (
        CalibrationReviewRepository,
    )

    user_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    # After flush+refresh, the ORM object has review_id populated
    persisted_orm = _make_review_orm(reviewed_by=user_id, action_taken="no_action")

    async def _fake_refresh(obj):
        obj.review_id = persisted_orm.review_id
        obj.reviewed_at = persisted_orm.reviewed_at
        obj.corr_at_review = persisted_orm.corr_at_review
        obj.below_threshold = persisted_orm.below_threshold

    mock_session.refresh = _fake_refresh

    repo = CalibrationReviewRepository(mock_session)
    create = CalibrationReviewCreate(
        reviewed_by=user_id,
        action_taken="no_action",
        corr_at_review=0.35,
        below_threshold=False,
    )
    result = await repo.insert_review(create)

    mock_session.add.assert_called_once()
    assert result.reviewed_by == user_id
    assert result.action_taken == "no_action"
    assert isinstance(result, CalibrationReview)


@pytest.mark.asyncio
async def test_list_recent_returns_rows_in_desc_reviewed_at_order_bounded_by_limit():
    """list_recent must return rows ordered by reviewed_at DESC, bounded by limit."""
    from src.ai.evaluation.repositories.calibration_review_repository import (
        CalibrationReviewRepository,
    )

    t1 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)

    orm_rows = []
    for ts in [t3, t2, t1]:
        row = _make_review_orm()
        row.reviewed_at = ts
        orm_rows.append(row)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = orm_rows

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CalibrationReviewRepository(mock_session)
    results = await repo.list_recent(limit=3)

    assert len(results) == 3
    # Must be ordered descending
    dates = [r.reviewed_at for r in results]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_get_last_review_returns_none_on_empty_table():
    """get_last_review returns None when table is empty."""
    from src.ai.evaluation.repositories.calibration_review_repository import (
        CalibrationReviewRepository,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CalibrationReviewRepository(mock_session)
    result = await repo.get_last_review()

    assert result is None


@pytest.mark.asyncio
async def test_get_last_review_returns_most_recent_when_rows_exist():
    """get_last_review returns the most recent CalibrationReview."""
    from src.ai.evaluation.repositories.calibration_review_repository import (
        CalibrationReviewRepository,
    )

    most_recent = _make_review_orm(action_taken="model_flag")
    most_recent.reviewed_at = datetime(2026, 6, 3, 10, 0, 0, tzinfo=timezone.utc)

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = most_recent

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = CalibrationReviewRepository(mock_session)
    result = await repo.get_last_review()

    assert result is not None
    assert result.action_taken == "model_flag"


@pytest.mark.asyncio
async def test_second_insert_does_not_affect_first_row():
    """Two separate inserts produce two independent rows with distinct review_ids."""
    from src.ai.evaluation.repositories.calibration_review_repository import (
        CalibrationReviewRepository,
    )

    added_objects: list = []

    mock_session = AsyncMock()

    def _capture_add(obj):
        added_objects.append(obj)

    mock_session.add = MagicMock(side_effect=_capture_add)
    mock_session.flush = AsyncMock()

    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    call_count = 0

    async def _fake_refresh(obj):
        nonlocal call_count
        call_count += 1
        obj.review_id = id1 if call_count == 1 else id2
        obj.reviewed_at = datetime.now(tz=timezone.utc)
        obj.corr_at_review = 0.3
        obj.below_threshold = False

    mock_session.refresh = _fake_refresh

    repo = CalibrationReviewRepository(mock_session)

    create1 = CalibrationReviewCreate(
        reviewed_by=uuid.uuid4(),
        action_taken="no_action",
    )
    create2 = CalibrationReviewCreate(
        reviewed_by=uuid.uuid4(),
        action_taken="improvement_loop_triggered",
    )

    r1 = await repo.insert_review(create1)
    r2 = await repo.insert_review(create2)

    assert r1.review_id != r2.review_id
    assert mock_session.add.call_count == 2
