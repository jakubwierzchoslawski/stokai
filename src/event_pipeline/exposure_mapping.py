"""
exposure_mapping.py — Steps 4 and 5 of the Mode A Reactive Pipeline.

Implements:
  - TrackedCompany: Pydantic model for a portfolio-tracked company.
  - ExposureRecord: Pydantic model for a computed exposure row.
  - compute_exposure_map: Step 4 — compute exposures for tracked companies.
  - persist_event_record: Step 5 — persist GeoEvent + EventExposure rows atomically.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from src.event_pipeline.pipeline_state import PipelineContext
from src.storage.repositories.company_exposure_repository import ICompanyRepository
from src.storage.repositories.event_exposure_repository import IEventExposureRepository
from src.storage.repositories.geo_event_repository import IGeoEventRepository


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class TrackedCompany(BaseModel):
    """A company tracked in the portfolio universe.

    Attributes:
        company_id: Unique identifier for the company.
        sector_internal: Internal sector classification string.
        sector_gics: GICS sector label.
        geo_revenue: Mapping of region name → revenue fraction (sums to ~1.0).
        market_cap_weight: This company's weight in the tracked universe [0, 1].
    """

    company_id: UUID
    sector_internal: str
    sector_gics: str
    geo_revenue: dict[str, float]  # region → fraction (sums to ~1.0)
    market_cap_weight: float  # company's weight in universe


class ExposureRecord(BaseModel):
    """A computed exposure for one company from one event.

    Attributes:
        company_id: The exposed company.
        magnitude: Computed exposure magnitude in [0, 1].
        direction: +1 (negative event → downward pressure) or -1 (positive event).
        geo_weight: Geographic revenue contribution to magnitude.
        sector_match: Sector contribution (0.0 or 1.0).
    """

    company_id: UUID
    magnitude: float
    direction: int  # +1 or -1
    geo_weight: float
    sector_match: float


# ---------------------------------------------------------------------------
# Step 4 — compute_exposure_map
# ---------------------------------------------------------------------------


async def compute_exposure_map(
    ctx: PipelineContext,
    company_repo: ICompanyRepository,
    exposure_threshold: float = 0.05,
) -> PipelineContext:
    """Compute an exposure map for all tracked companies from the pipeline context.

    For each tracked company:

        geo_weight = sum(geo_revenue.get(region, 0.0) for region in ctx.geo_regions)
        sector_match = (
            1.0 if ctx.sectors_affected and company.sector_internal in ctx.sectors_affected
            else 0.0
        )
        magnitude = (
            company.market_cap_weight
            * (geo_weight * 0.7 + sector_match * 0.3)
            * ctx.event_intensity / 5.0
        )
        direction = +1 if ctx.sentiment == "negative" else -1

    Only exposures with magnitude > exposure_threshold are included.

    Args:
        ctx: Current pipeline context (geo_regions, sectors_affected, event_intensity,
             sentiment, and tenant_id must be populated).
        company_repo: Repository providing access to tracked companies.
        exposure_threshold: Minimum magnitude to include an exposure record.
                            Defaults to 0.05.

    Returns:
        Updated PipelineContext with ``exposures`` list populated.
    """
    companies: list[TrackedCompany] = await company_repo.get_tracked_companies(
        ctx.tenant_id
    )

    exposures: list[ExposureRecord] = []

    for company in companies:
        # Geographic revenue contribution
        geo_weight: float = sum(
            company.geo_revenue.get(region, 0.0) for region in ctx.geo_regions
        )

        # Sector contribution
        sector_match: float = (
            1.0
            if ctx.sectors_affected and company.sector_internal in ctx.sectors_affected
            else 0.0
        )

        # Combined magnitude
        magnitude: float = (
            company.market_cap_weight
            * (geo_weight * 0.7 + sector_match * 0.3)
            * ctx.event_intensity
            / 5.0
        )

        # Direction: negative events create downward pressure (+1), positive events (-1)
        direction: int = 1 if ctx.sentiment == "negative" else -1

        if magnitude > exposure_threshold:
            exposures.append(
                ExposureRecord(
                    company_id=company.company_id,
                    magnitude=magnitude,
                    direction=direction,
                    geo_weight=geo_weight,
                    sector_match=sector_match,
                )
            )

    ctx.exposures = exposures  # type: ignore[assignment]
    return ctx


# ---------------------------------------------------------------------------
# Step 5 — persist_event_record
# ---------------------------------------------------------------------------


async def persist_event_record(
    ctx: PipelineContext,
    geo_event_repo: IGeoEventRepository,
    event_exposure_repo: IEventExposureRepository,
) -> PipelineContext:
    """Persist the GeoEvent row and all EventExposure rows atomically.

    Both inserts run inside the same database transaction (provided by the
    injected session). If the exposure bulk_insert raises, the exception
    propagates and the caller's session must roll back.

    Args:
        ctx: Pipeline context (geo_event_create, exposures, and tenant_id must be set).
        geo_event_repo: Repository for inserting/fetching geo_event rows.
        event_exposure_repo: Repository for bulk-inserting event_exposure rows.

    Returns:
        Updated context with ``event_id`` populated from the inserted row.
    """
    # Insert geo event row first
    geo_event = await geo_event_repo.insert(ctx.geo_event_create, ctx.tenant_id)
    ctx.event_id = geo_event.event_id

    # Bulk-insert all exposure records
    await event_exposure_repo.bulk_insert(geo_event.event_id, ctx.exposures, ctx.tenant_id)

    return ctx
