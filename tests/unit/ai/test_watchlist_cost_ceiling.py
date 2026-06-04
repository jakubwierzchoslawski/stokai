"""
Unit tests for cost ceiling enforcement at $1.00 for watchlist scan.

TDD: written before implementation — PLAN-F-008 TASK-015.

Tests:
  - Ceiling triggers at $1.00 (raises WorkflowCostLimitError)
  - Warning threshold at $0.80 (logged, not raised)
  - Guard created with $1.00 ceiling
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.watchlist_scan_nodes import (
    WATCHLIST_COST_CEILING_USD,
    _COST_WARNING_THRESHOLD_USD,
    detect_anomalies,
    filter_relevant_events,
    narrative_writer,
    run_watchlist_analyst,
)
from src.ai.workflows.watchlist_scan_state import WatchlistScanState


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


class TestWatchlistCostCeilingConstant:
    def test_cost_ceiling_is_1_usd(self):
        """WATCHLIST_COST_CEILING_USD must be 1.00."""
        assert WATCHLIST_COST_CEILING_USD == 1.00

    def test_warning_threshold_is_0_80(self):
        """_COST_WARNING_THRESHOLD_USD must be 0.80."""
        assert _COST_WARNING_THRESHOLD_USD == 0.80


class TestCostCeilingRaisesAtOneUSD:
    def test_guard_raises_at_exactly_1_00(self):
        """CostCeilingGuard with $1.00 ceiling raises when cost == $1.00."""
        guard = CostCeilingGuard(1.00)
        state = _make_state(cost_usd=1.00)

        with pytest.raises(WorkflowCostLimitError) as exc_info:
            guard.check(state)

        assert exc_info.value.ceiling == 1.00
        assert exc_info.value.accumulated == 1.00

    def test_guard_raises_when_cost_exceeds_1_00(self):
        """CostCeilingGuard raises when cost > $1.00."""
        guard = CostCeilingGuard(1.00)
        state = _make_state(cost_usd=1.05)

        with pytest.raises(WorkflowCostLimitError):
            guard.check(state)

    def test_guard_does_not_raise_below_ceiling(self):
        """CostCeilingGuard does not raise when cost < $1.00."""
        guard = CostCeilingGuard(1.00)
        state = _make_state(cost_usd=0.99)

        # Should not raise
        guard.check(state)

    def test_guard_ceiling_accessible_as_property(self):
        """CostCeilingGuard.ceiling_usd property returns the ceiling."""
        guard = CostCeilingGuard(WATCHLIST_COST_CEILING_USD)
        assert guard.ceiling_usd == WATCHLIST_COST_CEILING_USD

    @pytest.mark.asyncio
    async def test_filter_relevant_events_raises_at_ceiling(self):
        """filter_relevant_events raises at $1.00."""
        guard = CostCeilingGuard(1.00)
        agent = MagicMock()

        state = _make_state(cost_usd=1.00)
        with pytest.raises(WorkflowCostLimitError):
            await filter_relevant_events(state, agent=agent, cost_guard=guard)

    @pytest.mark.asyncio
    async def test_detect_anomalies_raises_at_ceiling(self):
        """detect_anomalies raises at $1.00."""
        guard = CostCeilingGuard(1.00)
        agent = MagicMock()

        state = _make_state(cost_usd=1.00)
        with pytest.raises(WorkflowCostLimitError):
            await detect_anomalies(state, agent=agent, cost_guard=guard)

    @pytest.mark.asyncio
    async def test_run_watchlist_analyst_raises_at_ceiling(self):
        """run_watchlist_analyst raises at $1.00."""
        guard = CostCeilingGuard(1.00)
        agent = MagicMock()

        state = _make_state(cost_usd=1.00)
        with pytest.raises(WorkflowCostLimitError):
            await run_watchlist_analyst(state, agent=agent, cost_guard=guard)

    @pytest.mark.asyncio
    async def test_narrative_writer_raises_at_ceiling(self):
        """narrative_writer raises at $1.00."""
        guard = CostCeilingGuard(1.00)
        agent = MagicMock()

        state = _make_state(cost_usd=1.00)
        with pytest.raises(WorkflowCostLimitError):
            await narrative_writer(state, agent=agent, cost_guard=guard)


class TestCostWarningThreshold:
    @pytest.mark.asyncio
    async def test_no_error_at_0_79(self, caplog):
        """No error at $0.79 (below warning threshold)."""
        import logging

        guard = CostCeilingGuard(1.00)
        output = MagicMock()
        output.cost_usd = 0.01
        output.relevant_events = []
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(cost_usd=0.79)
        with caplog.at_level(logging.WARNING):
            result = await filter_relevant_events(state, agent=agent, cost_guard=guard)

        # Should complete without error
        assert result is not None

    @pytest.mark.asyncio
    async def test_warning_logged_at_or_above_0_80(self, caplog):
        """Warning is logged when accumulated cost reaches $0.80."""
        import logging

        guard = CostCeilingGuard(1.00)
        output = MagicMock()
        output.cost_usd = 0.01  # total will be 0.80 + 0.01 = 0.81
        output.relevant_events = []
        agent = MagicMock()
        agent.invoke = MagicMock(return_value=output)

        state = _make_state(cost_usd=0.80)
        with caplog.at_level(logging.WARNING):
            result = await filter_relevant_events(state, agent=agent, cost_guard=guard)

        # Warning should be in logs
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("approaching ceiling" in msg or "0.8" in msg or "ceiling" in msg.lower()
                   for msg in warning_messages)
