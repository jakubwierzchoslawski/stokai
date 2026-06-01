"""Unit tests for PortfolioScanStep (TASK-006, TDD).

Tests written before implementation.
Covers: AC-001.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.pipeline_state import (
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_state_with_tickers(tickers: list[str]) -> PipelineState:
    tenant_id = uuid.uuid4()
    return PipelineState(
        raw_event_id=uuid.uuid4(),
        tenant_id=tenant_id,
        payload=RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload={"title": "event"},
            detected_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        ),
        event_description="Some geopolitical event",
        category=EventCategory.GEOPOLITICAL_CONFLICT,
        intensity=3,
        tickers=tickers,
    )


class TestPortfolioScanReturnsAffectedPortfolios:
    """test_portfolio_scan_returns_affected_portfolios"""

    @pytest.mark.asyncio
    async def test_portfolio_scan_returns_affected_portfolios(self):
        """PortfolioScanStep returns portfolios whose holdings overlap event tickers."""
        from src.event_pipeline.steps.s06_portfolio_scan import PortfolioScanStep

        portfolio_id_1 = uuid.uuid4()
        portfolio_id_2 = uuid.uuid4()

        # Mock portfolio data: portfolio_1 holds AAPL (overlaps), portfolio_2 holds MSFT (no overlap)
        mock_portfolios = [
            {"portfolio_id": str(portfolio_id_1), "holdings": {"AAPL": 0.3, "GOOGL": 0.7}},
            {"portfolio_id": str(portfolio_id_2), "holdings": {"MSFT": 0.5, "AMZN": 0.5}},
        ]

        repo_mock = AsyncMock()
        repo_mock.get_active_portfolios = AsyncMock(return_value=mock_portfolios)

        step = PortfolioScanStep(repo=repo_mock)
        state = _make_state_with_tickers(["AAPL", "TSLA"])

        result = await step.execute(state)

        assert str(portfolio_id_1) in result.exposure_map
        assert str(portfolio_id_2) not in result.exposure_map


class TestPortfolioScanReturnsEmptyForNoOverlap:
    """test_portfolio_scan_returns_empty_for_no_overlap"""

    @pytest.mark.asyncio
    async def test_portfolio_scan_returns_empty_for_no_overlap(self):
        """PortfolioScanStep returns empty exposure_map when no tickers overlap."""
        from src.event_pipeline.steps.s06_portfolio_scan import PortfolioScanStep

        portfolio_id = uuid.uuid4()
        mock_portfolios = [
            {"portfolio_id": str(portfolio_id), "holdings": {"MSFT": 1.0}},
        ]

        repo_mock = AsyncMock()
        repo_mock.get_active_portfolios = AsyncMock(return_value=mock_portfolios)

        step = PortfolioScanStep(repo=repo_mock)
        # Tickers in event do not appear in any portfolio
        state = _make_state_with_tickers(["NVDA", "AMD"])

        result = await step.execute(state)

        assert result.exposure_map == {}
