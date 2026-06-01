"""TDD tests for ConcreteGeoWeightCalculator (PLAN-F-003 TASK-008).

Tests written before implementation (red phase).
AC-004: geo_weight modifier recalculated and applied after live event updates.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from src.markets.config import MarketConfig, MarketRegistry


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_event(intensity: float, exposure_fraction: float) -> MagicMock:
    """Build a mock active geopolitical event."""
    event = MagicMock()
    event.intensity = intensity
    event.exposure_fraction = exposure_fraction
    return event


def _make_market(market_id: str, geo_weight_cap: float, enabled: bool = True) -> MarketConfig:
    return MarketConfig(
        market_id=market_id,
        display_name=market_id,
        price_provider="stub",
        fundamentals_provider="stub",
        news_provider="stub",
        currency="USD",
        trading_calendar="NYSE",
        enabled=enabled,
        geo_weight_cap=geo_weight_cap,
    )


class TestConcreteGeoWeightCalculator:
    """Unit tests for ConcreteGeoWeightCalculator."""

    @pytest.fixture
    def company_id(self):
        return uuid.uuid4()

    @pytest.fixture
    def tenant_id(self):
        return uuid.uuid4()

    def _make_calculator(self, events: list, market_cap: float = 2.0,
                         market_id: str = "US_EQUITIES", enabled: bool = True):
        """Build a calculator with injected mocks."""
        from src.scoring.geo_weight import ConcreteGeoWeightCalculator

        # Mock event tool returns the provided events
        event_tool = MagicMock()
        event_tool.get_active_events.return_value = events

        # Market registry with one market
        registry = MarketRegistry()
        registry.register(_make_market(market_id, geo_weight_cap=market_cap, enabled=enabled))

        return ConcreteGeoWeightCalculator(
            event_tool=event_tool,
            market_registry=registry,
            company_market_id=market_id,
        )

    def test_returns_1_when_no_active_events(self, company_id, tenant_id):
        """No active events → geo_weight = 1.0."""
        calc = self._make_calculator(events=[])
        result = calc.calculate(company_id, tenant_id)
        assert result == pytest.approx(1.0)

    def test_single_event_computes_correct_weight(self, company_id, tenant_id):
        """intensity=3, exposure=0.5 → raw=1+3*0.5=2.5, capped at 2.0."""
        events = [_make_event(intensity=3.0, exposure_fraction=0.5)]
        calc = self._make_calculator(events=events, market_cap=2.0)
        result = calc.calculate(company_id, tenant_id)
        assert result == pytest.approx(2.0)

    def test_single_event_below_cap(self, company_id, tenant_id):
        """intensity=1, exposure=0.2 → raw=1+1*0.2=1.2, below cap=2.0."""
        events = [_make_event(intensity=1.0, exposure_fraction=0.2)]
        calc = self._make_calculator(events=events, market_cap=2.0)
        result = calc.calculate(company_id, tenant_id)
        assert result == pytest.approx(1.2)

    def test_multiple_events_sum_correctly(self, company_id, tenant_id):
        """Two events with cap=3.0: raw=1+2*0.5+1*0.3=2.3, below cap."""
        events = [
            _make_event(intensity=2.0, exposure_fraction=0.5),
            _make_event(intensity=1.0, exposure_fraction=0.3),
        ]
        calc = self._make_calculator(events=events, market_cap=3.0)
        result = calc.calculate(company_id, tenant_id)
        assert result == pytest.approx(2.3)

    def test_cap_is_respected(self, company_id, tenant_id):
        """High-intensity stacked events never exceed geo_weight_cap."""
        events = [
            _make_event(intensity=5.0, exposure_fraction=1.0),
            _make_event(intensity=5.0, exposure_fraction=1.0),
            _make_event(intensity=5.0, exposure_fraction=1.0),
        ]
        calc = self._make_calculator(events=events, market_cap=2.0)
        result = calc.calculate(company_id, tenant_id)
        assert result == pytest.approx(2.0)
        assert result <= 2.0

    def test_cap_is_market_specific(self):
        """Two companies in markets with different caps produce different geo_weights."""
        from src.scoring.geo_weight import ConcreteGeoWeightCalculator

        events = [_make_event(intensity=5.0, exposure_fraction=1.0)]

        event_tool_a = MagicMock()
        event_tool_a.get_active_events.return_value = events
        registry_a = MarketRegistry()
        registry_a.register(_make_market("MARKET_A", geo_weight_cap=1.5))
        calc_a = ConcreteGeoWeightCalculator(
            event_tool=event_tool_a,
            market_registry=registry_a,
            company_market_id="MARKET_A",
        )

        event_tool_b = MagicMock()
        event_tool_b.get_active_events.return_value = events
        registry_b = MarketRegistry()
        registry_b.register(_make_market("MARKET_B", geo_weight_cap=3.0))
        calc_b = ConcreteGeoWeightCalculator(
            event_tool=event_tool_b,
            market_registry=registry_b,
            company_market_id="MARKET_B",
        )

        company_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        result_a = calc_a.calculate(company_id, tenant_id)
        result_b = calc_b.calculate(company_id, tenant_id)

        assert result_a == pytest.approx(1.5)
        assert result_b == pytest.approx(3.0)
        assert result_a != result_b

    def test_exposure_fraction_zero_contributes_nothing(self, company_id, tenant_id):
        """exposure_fraction=0.0 does not raise raw above 1.0."""
        events = [_make_event(intensity=5.0, exposure_fraction=0.0)]
        calc = self._make_calculator(events=events, market_cap=2.0)
        result = calc.calculate(company_id, tenant_id)
        assert result == pytest.approx(1.0)

    def test_market_config_not_found_uses_default_cap(self, company_id, tenant_id):
        """Unknown market_id falls back to default cap of 2.0."""
        from src.scoring.geo_weight import ConcreteGeoWeightCalculator

        events = [_make_event(intensity=5.0, exposure_fraction=1.0)]
        event_tool = MagicMock()
        event_tool.get_active_events.return_value = events
        registry = MarketRegistry()
        # No market registered

        calc = ConcreteGeoWeightCalculator(
            event_tool=event_tool,
            market_registry=registry,
            company_market_id="UNKNOWN_MARKET",
        )
        result = calc.calculate(company_id, tenant_id)
        assert result == pytest.approx(2.0)  # default cap
