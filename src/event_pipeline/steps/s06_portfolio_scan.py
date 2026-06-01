"""Step 6: PORTFOLIO SCAN — identify portfolios with affected holdings.

Architecture enforcement:
  P-01 Provider Abstraction — portfolio data accessed via repository only.
  AC-001 — populates exposure_map for Step 7 (exposure scoring).

Single Responsibility: portfolio discovery and ticker/category overlap detection.
Dependency Inversion: repository is injected.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


class PortfolioScanStep:
    """Pipeline Step 6: PORTFOLIO SCAN.

    Queries all active portfolios for the tenant and identifies which ones
    contain holdings that overlap with the event's affected tickers.

    Parameters
    ----------
    repo:
        Repository exposing ``get_active_portfolios(tenant_id) -> list[dict]``.
        Each dict contains ``portfolio_id`` and ``holdings`` (ticker -> weight).
    """

    step_name: str = "s06_portfolio_scan"

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    async def execute(self, state: PipelineState) -> PipelineState:
        """Identify portfolios with affected holdings."""
        portfolios = await self._repo.get_active_portfolios(state.tenant_id)

        event_tickers = set(state.tickers)
        exposure_map: dict[str, float] = {}

        for portfolio in portfolios:
            portfolio_id = str(portfolio["portfolio_id"])
            holdings = portfolio.get("holdings", {})
            holding_tickers = set(holdings.keys())

            if event_tickers & holding_tickers:
                # Initialise score to 0.0; ExposureScoreStep (Step 7) fills in the real value
                exposure_map[portfolio_id] = 0.0

        logger.info(
            "Step 6 (PORTFOLIO SCAN): raw_event_id=%s affected_portfolios=%d",
            state.raw_event_id,
            len(exposure_map),
        )

        return state.model_copy(update={"exposure_map": exposure_map})
