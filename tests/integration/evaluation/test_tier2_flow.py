"""
Integration tests for Tier-2 regression flow.

Tests the full path: Tier2RunnerService → GoldenDatasetRepository → RegressionReport.
Uses mocked agent runner (no real LLM calls).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.evaluation.schemas.calibration_schemas import RegressionReport
from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItem


def _make_active_item() -> GoldenDatasetItem:
    return GoldenDatasetItem(
        item_id=uuid.uuid4(),
        input={"query": "Analyse AAPL"},
        expected_output={"signal": "BUY", "confidence": 0.8},
        quality_metrics={
            "factual_grounding": 0.9,
            "confidence_calibration": 0.85,
        },
        source="hand_authored",
        active=True,
        created_at=datetime.now(tz=timezone.utc),
    )


# ── insufficient dataset ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_flow_insufficient_dataset():
    """Integration: fewer than 20 active items produces insufficient_dataset report."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    mock_repo = AsyncMock()
    mock_repo.list_active = AsyncMock(
        return_value=[_make_active_item() for _ in range(10)]
    )

    service = Tier2RunnerService(golden_dataset_repo=mock_repo)
    report = await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="analyst",
    )

    assert report.passed is False
    assert report.reason == "insufficient_dataset"


# ── passing regression ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_flow_passes_when_candidate_improves(tmp_path, monkeypatch):
    """Integration: candidate improves all metrics → passed=True, no breached metrics."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    mock_repo = AsyncMock()
    mock_repo.list_active = AsyncMock(
        return_value=[_make_active_item() for _ in range(20)]
    )

    async def _mock_run(item, prompt_version, agent_role):
        if prompt_version == "v1":
            return {"factual_grounding": 0.7, "calibration": 0.75}
        # candidate improves both metrics
        return {"factual_grounding": 0.8, "calibration": 0.85}

    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(side_effect=_mock_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_repo,
        agent_runner=mock_runner,
    )
    report = await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="analyst",
    )

    assert report.passed is True
    assert len(report.breached_metrics) == 0
    assert report.per_metric_delta["factual_grounding"] > 0


# ── failing regression ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_flow_fails_when_candidate_regresses(tmp_path, monkeypatch):
    """Integration: candidate regresses beyond threshold → passed=False."""
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    mock_repo = AsyncMock()
    mock_repo.list_active = AsyncMock(
        return_value=[_make_active_item() for _ in range(20)]
    )

    async def _mock_run(item, prompt_version, agent_role):
        if prompt_version == "v1":
            return {"quality": 0.8}
        # 20% regression — well beyond the 5% threshold
        return {"quality": 0.64}

    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(side_effect=_mock_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_repo,
        agent_runner=mock_runner,
    )
    report = await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="analyst",
    )

    assert report.passed is False
    assert "quality" in report.breached_metrics


# ── log file persisted ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier2_flow_regression_log_written(tmp_path, monkeypatch):
    """Integration: regression log JSON is written to the log directory."""
    import json as _json

    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    mock_repo = AsyncMock()
    mock_repo.list_active = AsyncMock(
        return_value=[_make_active_item() for _ in range(20)]
    )

    async def _mock_run(item, prompt_version, agent_role):
        return {"quality": 0.8}

    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(side_effect=_mock_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_repo,
        agent_runner=mock_runner,
    )
    await service.run_regression(
        prompt_version_candidate="v2",
        prompt_version_production="v1",
        agent_role="analyst",
    )

    log_files = list(tmp_path.glob("*.json"))
    assert len(log_files) == 1

    with open(log_files[0]) as f:
        log_data = _json.load(f)

    assert "passed" in log_data
    assert "per_metric_delta" in log_data
    assert log_data["item_count"] == 20
