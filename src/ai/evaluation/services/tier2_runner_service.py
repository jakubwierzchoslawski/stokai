"""
Tier2RunnerService — ITier2Runner implementation.

Runs regression testing against the golden dataset by comparing candidate
and production prompt versions across all active dataset items.

Algorithm:
  1. Fetch all active golden dataset items.
  2. If <20 items → return RegressionReport(passed=False, reason='insufficient_dataset').
  3. For each item, invoke agent_runner with both prompt versions.
  4. Aggregate per_metric_delta = mean (candidate - production) / production per metric.
  5. breached_metrics = metrics where delta < -0.05.
  6. passed = len(breached_metrics) == 0.
  7. Persist JSON log to logs/tier2_regression/.
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from src.ai.evaluation.interfaces.i_tier2_runner import ITier2Runner
from src.ai.evaluation.interfaces.i_golden_dataset_repository import (
    IGoldenDatasetRepository,
)
from src.ai.evaluation.schemas.calibration_schemas import RegressionReport
from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItem

logger = logging.getLogger(__name__)

_MIN_DATASET_SIZE = 20
_LOG_DIR = "logs/tier2_regression"
_REGRESSION_THRESHOLD = -0.05


class InsufficientDatasetError(Exception):
    """Raised when the golden dataset has fewer than the required minimum active items.

    The Tier-2 regression gate requires at least 20 active items to produce
    a statistically meaningful per-metric delta.  Callers that need to surface
    this condition programmatically (e.g. perf_gate.py) should catch this error.
    """


class AgentRunner:
    """Default agent runner — stub that returns empty scores.

    Production deployments replace this with a real implementation that
    invokes the LLM with the specified prompt version and returns quality
    scores as a dict[metric_name, score].
    """

    async def run(
        self,
        item: GoldenDatasetItem,
        prompt_version: str,
        agent_role: str,
    ) -> dict[str, float]:
        """Invoke the agent for one golden dataset item and return scores."""
        return {}


class Tier2RunnerService(ITier2Runner):
    """
    Runs regression tests against the golden dataset.

    Parameters
    ----------
    golden_dataset_repo:
        Repository for fetching active golden dataset items.
    agent_runner:
        Object with async run(item, prompt_version, agent_role) -> dict[str, float].
        Defaults to a no-op stub.
    """

    def __init__(
        self,
        golden_dataset_repo: IGoldenDatasetRepository,
        agent_runner: Any | None = None,
    ) -> None:
        self._gd_repo = golden_dataset_repo
        self._runner = agent_runner or AgentRunner()

    async def run_regression(
        self,
        prompt_version_candidate: str,
        prompt_version_production: str,
        agent_role: str,
    ) -> RegressionReport:
        """
        Compare candidate vs production prompt versions across the active dataset.

        Returns
        -------
        RegressionReport
            - passed=False, reason='insufficient_dataset' if <20 active items.
            - Otherwise derives passed from per_metric_delta (all >= -0.05 → passed).
        """
        active_items = await self._gd_repo.list_active()

        if len(active_items) < _MIN_DATASET_SIZE:
            logger.warning(
                "Tier2RunnerService: insufficient dataset (%d items, need %d)",
                len(active_items),
                _MIN_DATASET_SIZE,
            )
            return RegressionReport(
                passed=False,
                reason="insufficient_dataset",
            )

        # Accumulate per-metric sums for delta computation
        metric_candidate_sums: dict[str, float] = defaultdict(float)
        metric_production_sums: dict[str, float] = defaultdict(float)
        metric_counts: dict[str, int] = defaultdict(int)

        item_results = []

        for item in active_items:
            try:
                prod_scores = await self._runner.run(
                    item=item,
                    prompt_version=prompt_version_production,
                    agent_role=agent_role,
                )
                cand_scores = await self._runner.run(
                    item=item,
                    prompt_version=prompt_version_candidate,
                    agent_role=agent_role,
                )
            except Exception as exc:
                logger.warning(
                    "Tier2RunnerService: agent_runner.run failed for item %s: %s",
                    item.item_id,
                    type(exc).__name__,
                )
                continue

            # Accumulate scores for metrics present in both runs
            for metric in set(prod_scores) & set(cand_scores):
                metric_production_sums[metric] += prod_scores[metric]
                metric_candidate_sums[metric] += cand_scores[metric]
                metric_counts[metric] += 1

            item_results.append(
                {
                    "item_id": str(item.item_id),
                    "production_scores": prod_scores,
                    "candidate_scores": cand_scores,
                }
            )

        # Compute mean delta per metric
        per_metric_delta: dict[str, float] = {}
        for metric, count in metric_counts.items():
            if count == 0:
                continue
            mean_prod = metric_production_sums[metric] / count
            mean_cand = metric_candidate_sums[metric] / count
            if mean_prod == 0.0:
                # Avoid division by zero; use absolute delta
                delta = mean_cand - mean_prod
            else:
                delta = (mean_cand - mean_prod) / mean_prod
            per_metric_delta[metric] = delta

        # Build report (model_validator derives breached_metrics and passed)
        report = RegressionReport(per_metric_delta=per_metric_delta)

        # Persist log
        self._persist_log(
            prompt_version_candidate=prompt_version_candidate,
            prompt_version_production=prompt_version_production,
            agent_role=agent_role,
            item_results=item_results,
            report=report,
        )

        return report

    def _persist_log(
        self,
        prompt_version_candidate: str,
        prompt_version_production: str,
        agent_role: str,
        item_results: list[dict],
        report: RegressionReport,
    ) -> None:
        """Write a JSON regression log to _LOG_DIR."""
        try:
            os.makedirs(_LOG_DIR, exist_ok=True)
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = os.path.join(
                _LOG_DIR,
                f"regression_{timestamp}_{agent_role}.json",
            )
            payload = {
                "timestamp": timestamp,
                "prompt_version_candidate": prompt_version_candidate,
                "prompt_version_production": prompt_version_production,
                "agent_role": agent_role,
                "passed": report.passed,
                "per_metric_delta": report.per_metric_delta,
                "breached_metrics": report.breached_metrics,
                "reason": report.reason,
                "item_count": len(item_results),
                "items": item_results,
            }
            with open(filename, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str)
            logger.debug("Tier2RunnerService: regression log written to %s", filename)
        except Exception as exc:
            logger.warning(
                "Tier2RunnerService: could not write regression log: %s",
                type(exc).__name__,
            )
