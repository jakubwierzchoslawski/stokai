"""
ITier2Runner — abstract interface for Tier-2 regression testing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.ai.evaluation.schemas.calibration_schemas import RegressionReport


class ITier2Runner(ABC):
    """Runs regression tests against the golden dataset."""

    @abstractmethod
    async def run_regression(
        self,
        prompt_version_candidate: str,
        prompt_version_production: str,
        agent_role: str,
    ) -> RegressionReport:
        """
        Run a regression comparison between candidate and production prompt versions.

        Returns a RegressionReport where:
        - per_metric_delta[m] = (candidate_score - production_score) / production_score
        - breached_metrics: metrics where delta < -0.05
        - passed = len(breached_metrics) == 0
        - If dataset has fewer than 20 active items, returns passed=False,
          reason='insufficient_dataset'.
        """
        ...
