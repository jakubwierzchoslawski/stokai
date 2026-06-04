"""
PLAN-N-009 TASK-001 — Per-metric gate unit tests.

Verifies that Tier2RunnerService.run_regression() enforces the per-metric
5% threshold correctly.  The critical invariant: a single metric breaching
-5% must produce passed=False even if all other metrics improve substantially.
No aggregation or weighted averaging is permitted.

AC-001, AC-002.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_METRICS_ALL = [
    "coherence",
    "factual_accuracy",
    "action_signal_correctness",
    "recommendation_quality",
    "confidence_calibration",
]


def _make_item() -> GoldenDatasetItem:
    return GoldenDatasetItem(
        item_id=uuid.uuid4(),
        input={"query": "Analyse TSLA"},
        expected_output={"signal": "HOLD", "confidence": 0.75},
        quality_metrics={m: 0.8 for m in _METRICS_ALL},
        source="hand_authored",
        active=True,
        created_at=datetime.now(tz=timezone.utc),
    )


def _make_repo_with_20_items() -> AsyncMock:
    repo = AsyncMock()
    repo.list_active = AsyncMock(return_value=[_make_item() for _ in range(20)])
    return repo


def _make_runner_from_deltas(
    production_base: float,
    candidate_deltas: dict[str, float],
) -> Any:
    """
    Return a mock agent runner that always returns production_base for prod,
    and production_base * (1 + delta) for the candidate.

    candidate_deltas: metric -> fractional delta (e.g. 0.10 = +10%)
    """
    prod_scores = {m: production_base for m in candidate_deltas}
    cand_scores = {m: production_base * (1.0 + d) for m, d in candidate_deltas.items()}

    async def _run(item: Any, prompt_version: str, agent_role: str) -> dict[str, float]:
        # First call per item is production, second is candidate.
        # We distinguish by prompt_version convention in the test.
        if prompt_version == "prod-sha":
            return dict(prod_scores)
        return dict(cand_scores)

    runner = MagicMock()
    runner.run = AsyncMock(side_effect=_run)
    return runner


# ---------------------------------------------------------------------------
# TASK-001 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_metric_breach_blocks_regardless_of_improvements(
    tmp_path, monkeypatch
):
    """
    Candidate: coherence +10%, factual_accuracy +5%, action_signal_correctness -6%,
               recommendation_quality +3%, confidence_calibration +8%.
    Expected: passed=False, breached_metrics == ['action_signal_correctness'].
    """
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    deltas = {
        "coherence": 0.10,
        "factual_accuracy": 0.05,
        "action_signal_correctness": -0.06,
        "recommendation_quality": 0.03,
        "confidence_calibration": 0.08,
    }

    service = Tier2RunnerService(
        golden_dataset_repo=_make_repo_with_20_items(),
        agent_runner=_make_runner_from_deltas(1.0, deltas),
    )

    report = await service.run_regression(
        prompt_version_candidate="cand-sha",
        prompt_version_production="prod-sha",
        agent_role="recommendation-analyst",
    )

    assert report.passed is False
    assert "action_signal_correctness" in report.breached_metrics
    # No other metric should appear in breached_metrics
    assert len(report.breached_metrics) == 1


@pytest.mark.asyncio
async def test_two_metrics_below_threshold_both_appear_in_breached(
    tmp_path, monkeypatch
):
    """
    Candidate: coherence -7%, factual_accuracy -6%, action_signal_correctness +2%.
    Expected: passed=False; both 'coherence' and 'factual_accuracy' in breached_metrics.
    """
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    deltas = {
        "coherence": -0.07,
        "factual_accuracy": -0.06,
        "action_signal_correctness": 0.02,
    }

    service = Tier2RunnerService(
        golden_dataset_repo=_make_repo_with_20_items(),
        agent_runner=_make_runner_from_deltas(1.0, deltas),
    )

    report = await service.run_regression(
        prompt_version_candidate="cand-sha",
        prompt_version_production="prod-sha",
        agent_role="recommendation-analyst",
    )

    assert report.passed is False
    assert "coherence" in report.breached_metrics
    assert "factual_accuracy" in report.breached_metrics
    assert "action_signal_correctness" not in report.breached_metrics


@pytest.mark.asyncio
async def test_exactly_at_threshold_does_not_breach(tmp_path, monkeypatch):
    """
    action_signal_correctness delta == -0.05 exactly.
    Gate fires on < -0.05, not <= -0.05.  Expected: passed=True.
    """
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    # Construct scores so (cand - prod) / prod == exactly -0.05.
    # prod=20.0, cand=19.0 → (19.0-20.0)/20.0 = -0.05 exactly in IEEE 754.
    PROD = 20.0
    CAND = 19.0

    async def _exact_run(item: Any, prompt_version: str, agent_role: str) -> dict[str, float]:
        if prompt_version == "prod-sha":
            return {"action_signal_correctness": PROD}
        return {"action_signal_correctness": CAND}

    exact_runner = MagicMock()
    exact_runner.run = AsyncMock(side_effect=_exact_run)

    service = Tier2RunnerService(
        golden_dataset_repo=_make_repo_with_20_items(),
        agent_runner=exact_runner,
    )

    report = await service.run_regression(
        prompt_version_candidate="cand-sha",
        prompt_version_production="prod-sha",
        agent_role="recommendation-analyst",
    )

    assert report.passed is True
    assert report.breached_metrics == []


@pytest.mark.asyncio
async def test_just_over_threshold_breaches(tmp_path, monkeypatch):
    """
    action_signal_correctness delta == -0.051.
    Expected: passed=False.
    """
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    # prod=1000.0, cand=949.0 → (949-1000)/1000 = -0.051 exactly in IEEE 754.
    PROD = 1000.0
    CAND = 949.0

    async def _over_run(item: Any, prompt_version: str, agent_role: str) -> dict[str, float]:
        if prompt_version == "prod-sha":
            return {"action_signal_correctness": PROD}
        return {"action_signal_correctness": CAND}

    over_runner = MagicMock()
    over_runner.run = AsyncMock(side_effect=_over_run)

    service = Tier2RunnerService(
        golden_dataset_repo=_make_repo_with_20_items(),
        agent_runner=over_runner,
    )

    report = await service.run_regression(
        prompt_version_candidate="cand-sha",
        prompt_version_production="prod-sha",
        agent_role="recommendation-analyst",
    )

    assert report.passed is False
    assert "action_signal_correctness" in report.breached_metrics


@pytest.mark.asyncio
async def test_all_metrics_improving_passes(tmp_path, monkeypatch):
    """
    All deltas positive.  Expected: passed=True, breached_metrics == [].
    """
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    deltas = {
        "coherence": 0.08,
        "factual_accuracy": 0.12,
        "action_signal_correctness": 0.04,
        "recommendation_quality": 0.01,
        "confidence_calibration": 0.05,
    }

    service = Tier2RunnerService(
        golden_dataset_repo=_make_repo_with_20_items(),
        agent_runner=_make_runner_from_deltas(1.0, deltas),
    )

    report = await service.run_regression(
        prompt_version_candidate="cand-sha",
        prompt_version_production="prod-sha",
        agent_role="recommendation-analyst",
    )

    assert report.passed is True
    assert report.breached_metrics == []


@pytest.mark.asyncio
async def test_mixed_result_ac002_scenario(tmp_path, monkeypatch):
    """
    AC-002 scenario: 2% and 4% degradation on two metrics, 6% on a third.
    Expected: passed=False; only the 6%-breaching metric in breached_metrics.
    """
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    deltas = {
        "coherence": -0.02,               # within tolerance
        "factual_accuracy": -0.04,        # within tolerance
        "action_signal_correctness": -0.06,  # breaches
    }

    service = Tier2RunnerService(
        golden_dataset_repo=_make_repo_with_20_items(),
        agent_runner=_make_runner_from_deltas(1.0, deltas),
    )

    report = await service.run_regression(
        prompt_version_candidate="cand-sha",
        prompt_version_production="prod-sha",
        agent_role="recommendation-analyst",
    )

    assert report.passed is False
    assert "action_signal_correctness" in report.breached_metrics
    # coherence and factual_accuracy are within tolerance — must NOT appear
    assert "coherence" not in report.breached_metrics
    assert "factual_accuracy" not in report.breached_metrics
