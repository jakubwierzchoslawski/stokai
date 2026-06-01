"""GeoWeight Calculator implementation (PLAN-F-003 TASK-008).

Implements ``ConcreteGeoWeightCalculator`` satisfying the
``GeoWeightCalculator`` Protocol.

Formula (OQ-1, PLAN-F-003 Brainstorm Decision):
    geo_weight = min(1.0 + Σ(event.intensity * event.exposure_fraction), cap)

where:
    cap = geo_weight_cap from the company's MarketConfig (default 2.0)
    intensity ∈ [1, 5]
    exposure_fraction ∈ [0.0, 1.0]

Returns 1.0 when no active events affect the company's region.

Dependency inversion (P-01, DIP):
    - ``event_tool`` is an injected adapter; never imported directly.
    - ``market_registry`` is an injected MarketRegistry; not a global import.
"""
from __future__ import annotations

from uuid import UUID

from src.markets.config import MarketRegistry

_DEFAULT_GEO_WEIGHT_CAP = 2.0


class ConcreteGeoWeightCalculator:
    """Computes the geo_weight multiplier for a company.

    Parameters
    ----------
    event_tool:
        An object with a ``get_active_events(company_id, tenant_id)`` method
        that returns a list of active geopolitical event objects.  Each event
        must expose ``intensity`` (float) and ``exposure_fraction`` (float).
    market_registry:
        The ``MarketRegistry`` used to look up the ``geo_weight_cap`` for the
        company's market.
    company_market_id:
        The market_id string for the company being scored.  In a full
        implementation this would be resolved dynamically from the company's
        holdings data; for MVP it is injected at construction time to keep
        the interface stateless per ``calculate()`` call.
    """

    def __init__(
        self,
        event_tool: object,
        market_registry: MarketRegistry,
        company_market_id: str = "",
    ) -> None:
        self._event_tool = event_tool
        self._market_registry = market_registry
        self._company_market_id = company_market_id

    def calculate(self, company_id: UUID, tenant_id: UUID) -> float:
        """Return the geo_weight multiplier for *company_id* within *tenant_id*.

        Steps:
        1. Retrieve active events via ``event_tool.get_active_events()``.
        2. Compute raw = 1.0 + Σ(intensity × exposure_fraction).
        3. Retrieve geo_weight_cap from MarketConfig (defaults to 2.0 if not found).
        4. Return min(raw, cap).

        Returns
        -------
        float
            Geo_weight ∈ [1.0, cap]. Always 1.0 when no active events.
        """
        active_events = self._event_tool.get_active_events(company_id, tenant_id)

        if not active_events:
            return 1.0

        raw = 1.0 + sum(
            float(e.intensity) * float(e.exposure_fraction)
            for e in active_events
        )

        cap = self._resolve_cap()
        return min(raw, cap)

    def _resolve_cap(self) -> float:
        """Return the geo_weight_cap for the company's market."""
        if self._company_market_id:
            config = self._market_registry.get_market_config(self._company_market_id)
            if config is not None:
                return config.geo_weight_cap
        return _DEFAULT_GEO_WEIGHT_CAP
