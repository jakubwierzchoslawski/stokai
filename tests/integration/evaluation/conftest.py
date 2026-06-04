"""
PLAN-N-009 TASK-005 — Fixtures for integration/evaluation tests.

Provides:
- golden_dataset_20_items: seeds exactly 20 active GoldenDatasetItem rows
  in a mock repository for use by test_regression_perf.py (TASK-003).

The fixture returns a list of GoldenDatasetItem objects and a compatible
AsyncMock repository that list_active() returns them from.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator, NamedTuple
from unittest.mock import AsyncMock

import pytest

from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(index: int = 0) -> GoldenDatasetItem:
    return GoldenDatasetItem(
        item_id=uuid.uuid4(),
        input={"query": f"Analyse TICKER{index:03d}", "event_type": "earnings"},
        expected_output={"signal": "BUY", "confidence": 0.75 + (index % 5) * 0.02},
        quality_metrics={
            "coherence": 0.80,
            "factual_accuracy": 0.82,
            "action_signal_correctness": 0.78,
            "recommendation_quality": 0.79,
            "confidence_calibration": 0.81,
        },
        source="hand_authored",
        active=True,
        created_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Named tuple returned by the fixture
# ---------------------------------------------------------------------------


class GoldenDatasetFixture(NamedTuple):
    items: list[GoldenDatasetItem]
    repo: AsyncMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def golden_dataset_20_items() -> Generator[GoldenDatasetFixture, None, None]:
    """Seed exactly 20 active GoldenDatasetItem rows in a mock repository.

    Returns a GoldenDatasetFixture(items, repo) namedtuple.
    - items: list of 20 GoldenDatasetItem instances.
    - repo: AsyncMock whose list_active() returns those 20 items.

    Usage in test_regression_perf.py::
        async def test_something(golden_dataset_20_items):
            service = Tier2RunnerService(
                golden_dataset_repo=golden_dataset_20_items.repo,
                agent_runner=my_stub_runner,
            )
            report = await service.run_regression(...)
    """
    items = [_make_item(i) for i in range(20)]
    repo = AsyncMock()
    repo.list_active = AsyncMock(return_value=items)
    yield GoldenDatasetFixture(items=items, repo=repo)
