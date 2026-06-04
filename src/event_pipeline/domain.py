"""
event_pipeline.domain — Shared domain models for the event pipeline.

These models are kept in a separate module to avoid circular imports between
company_exposure_repository and exposure_mapping.

PLAN-F-023: extracted TrackedCompany here to break circular dependency.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class TrackedCompany(BaseModel):
    """A company tracked in the portfolio universe.

    Attributes:
        company_id: Unique identifier for the company.
        sector_internal: Internal sector classification string.
        sector_gics: GICS sector label.
        geo_revenue: Mapping of region name -> revenue fraction (sums to ~1.0).
        market_cap_weight: This company's weight in the tracked universe [0, 1].
    """

    company_id: UUID
    sector_internal: str
    sector_gics: str
    geo_revenue: dict[str, float]  # region -> fraction (sums to ~1.0)
    market_cap_weight: float  # company's weight in universe
