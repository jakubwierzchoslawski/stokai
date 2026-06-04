"""
Unit tests for TASK-007: Tier2RunnerService.

TDD: written before the implementation exists.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.evaluation.schemas.calibration_schemas import RegressionReport
from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItem
from datetime import datetime, timezone


def _make_golden_item(item_id: uuid.UUID | None = None) -> GoldenDatasetItem:
    return GoldenDatasetItem(
        item_id=item_id or uuid.uuid4(),
        input={"query": "Analyse AAPL"},
        expected_output={"signal": "BUY", "confidence": 0.8},
        quality_metrics={
            "factual_grounding": 0.9,
            "confidence_calibration": 0.85,
            "internal_consistency": 0.8,
        },
        source="hand_authored",
        active=True,
        created_at=datetime.now(tz=timezone.utc),
    )


# ── insufficient dataset ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_runner_insufficient_dataset_returns_failed():
    """run_regression with <20 active items should return passed=False, reason='insufficient_dataset'."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    mock_gd_repo = AsyncMock()
    # Only 5 items — below the 20-item threshold
    mock_gd_repo.list_active = AsyncMock(
        return_value=[_make_golden_item() for _ in range(5)]
    )

    mock_agent_runner = MagicMock()
    service = Tier2RunnerService(
        golden_dataset_repo=mock_gd_repo,
        agent_runner=mock_agent_runner,
    )

    report = await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="recommendation-analyst",
    )

    assert report.passed is False
    assert report.reason == "insufficient_dataset"


@pytest.mark.asyncio
async def test_tier2_runner_exactly_20_items_proceeds():
    """run_regression with exactly 20 active items should NOT return insufficient_dataset."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    mock_gd_repo = AsyncMock()
    mock_gd_repo.list_active = AsyncMock(
        return_value=[_make_golden_item() for _ in range(20)]
    )

    async def _mock_run(item: Any, prompt_version: str, agent_role: str) -> dict[str, float]:
        return {"factual_grounding": 0.85, "confidence_calibration": 0.80}

    mock_agent_runner = MagicMock()
    mock_agent_runner.run = AsyncMock(side_effect=_mock_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_gd_repo,
        agent_runner=mock_agent_runner,
    )

    report = await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="recommendation-analyst",
    )

    # With same scores for candidate and production (delta=0), should pass
    assert report.reason != "insufficient_dataset"


# ── per_metric_delta computation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_runner_delta_computation():
    """per_metric_delta = (candidate - production) / production per metric."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    mock_gd_repo = AsyncMock()
    mock_gd_repo.list_active = AsyncMock(
        return_value=[_make_golden_item() for _ in range(20)]
    )

    call_count = {"n": 0}

    async def _mock_run(item: Any, prompt_version: str, agent_role: str) -> dict[str, float]:
        call_count["n"] += 1
        # production scores are always 0.8
        if prompt_version == "v1":
            return {"quality": 0.8}
        # candidate scores are always 0.9 (improvement)
        return {"quality": 0.9}

    mock_agent_runner = MagicMock()
    mock_agent_runner.run = AsyncMock(side_effect=_mock_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_gd_repo,
        agent_runner=mock_agent_runner,
    )

    report = await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="analyst",
    )

    # delta = (0.9 - 0.8) / 0.8 = 0.125 (improvement) → passed
    assert "quality" in report.per_metric_delta
    assert abs(report.per_metric_delta["quality"] - 0.125) < 0.01
    assert report.passed is True


# ── breached_metrics ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_runner_breached_metrics_when_delta_below_threshold():
    """Metrics with delta < -0.05 should appear in breached_metrics; passed=False."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    mock_gd_repo = AsyncMock()
    mock_gd_repo.list_active = AsyncMock(
        return_value=[_make_golden_item() for _ in range(20)]
    )

    async def _mock_run(item: Any, prompt_version: str, agent_role: str) -> dict[str, float]:
        if prompt_version == "v1":
            return {"quality": 0.8}
        # candidate is 15% worse: delta = (0.68 - 0.8) / 0.8 = -0.15
        return {"quality": 0.68}

    mock_agent_runner = MagicMock()
    mock_agent_runner.run = AsyncMock(side_effect=_mock_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_gd_repo,
        agent_runner=mock_agent_runner,
    )

    report = await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="analyst",
    )

    assert "quality" in report.breached_metrics
    assert report.passed is False


# ── regression log persisted ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_runner_persists_regression_log(tmp_path, monkeypatch):
    """run_regression should write a JSON log to logs/tier2_regression/."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    # Redirect log path to tmp_path
    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    mock_gd_repo = AsyncMock()
    mock_gd_repo.list_active = AsyncMock(
        return_value=[_make_golden_item() for _ in range(20)]
    )

    async def _mock_run(item: Any, prompt_version: str, agent_role: str) -> dict[str, float]:
        return {"quality": 0.8}

    mock_agent_runner = MagicMock()
    mock_agent_runner.run = AsyncMock(side_effect=_mock_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_gd_repo,
        agent_runner=mock_agent_runner,
    )

    await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="analyst",
    )

    # Check that a log file was written
    log_files = list(tmp_path.glob("*.json"))
    assert len(log_files) == 1
