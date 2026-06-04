"""
Step 4 — compute_exposure_map.

Queries the company table to find companies exposed to the classified event
via geography, sector, or direct ticker match.
"""
from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.events.models import ExposureCandidate, PipelineContext

# Simple heuristic: if classification sentiment is "negative" the direction is "negative"
_DEFAULT_DIRECTION = "negative"
_DEFAULT_MAGNITUDE = 0.5
_DIRECT_MAGNITUDE = 1.0

# Geo region → ISO country code prefix mapping (simplified)
_REGION_COUNTRY_MAP: dict[str, list[str]] = {
    "EMEA": ["DE", "FR", "GB", "IT", "ES", "NL", "SA", "AE", "ZA", "EG"],
    "APAC": ["CN", "JP", "KR", "AU", "IN", "SG", "HK", "TW"],
    "LATAM": ["BR", "MX", "AR", "CL", "CO", "PE"],
    "North America": ["US", "CA", "MX"],
    "Global": [],  # matches all
}


def _get_countries_for_regions(regions: list[str]) -> list[str]:
    """Expand geo region labels into country code lists."""
    countries: list[str] = []
    for region in regions:
        if region == "Global":
            return []  # Empty means no country filter (match all)
        countries.extend(_REGION_COUNTRY_MAP.get(region, [region]))
    return list(set(countries))


async def compute_exposure_map(
    ctx: PipelineContext,
    db_session: AsyncSession,
) -> PipelineContext:
    """Map event classification to affected companies.

    Args:
        ctx: Current pipeline context (classification and tickers must be set).
        db_session: Async DB session for company table queries.

    Returns:
        Updated context with exposures list populated.
    """
    classification = ctx.classification
    geo_regions = classification.geo_regions if classification else []
    affected_sectors = classification.affected_sectors if classification else []
    tickers = ctx.tickers or []

    # Short-circuit if nothing to match on
    if not geo_regions and not affected_sectors and not tickers:
        ctx.step_latencies_ms["compute_exposure_map"] = 0
        return ctx

    direction = "negative"
    if classification and classification.sentiment == "positive":
        direction = "positive"

    t0 = time.monotonic()
    countries = _get_countries_for_regions(geo_regions)

    stmt = text(
        """
        SELECT
            company_id,
            ticker,
            sector_internal,
            hq_country,
            geo_revenue
        FROM company
        WHERE
            (:has_tickers AND ticker = ANY(:tickers))
            OR (:has_sectors AND sector_internal = ANY(:sectors))
            OR (:has_countries AND hq_country = ANY(:countries))
        """
    )

    result = await db_session.execute(
        stmt,
        {
            "has_tickers": bool(tickers),
            "tickers": tickers or [],
            "has_sectors": bool(affected_sectors),
            "sectors": affected_sectors or [],
            "has_countries": bool(countries),
            "countries": countries or [],
        },
    )

    rows = list(result.mappings())
    exposures: list[ExposureCandidate] = []

    for row in rows:
        company_id: UUID = row["company_id"]
        ticker: str = row["ticker"] or ""
        sector: str = row["sector_internal"] or ""
        hq_country: str = row["hq_country"] or ""

        # Determine primary exposure type (priority: direct > sector > currency)
        if ticker in tickers:
            exposure_type = "direct"
            magnitude = _DIRECT_MAGNITUDE
        elif sector in affected_sectors:
            exposure_type = "sector"
            magnitude = _DEFAULT_MAGNITUDE
        elif hq_country in countries:
            exposure_type = "currency"
            magnitude = _DEFAULT_MAGNITUDE
        else:
            continue  # Should not happen due to WHERE clause but guard anyway

        exposures.append(
            ExposureCandidate(
                company_id=company_id,
                exposure_type=exposure_type,
                direction=direction,
                magnitude=magnitude,
            )
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    ctx.exposures = exposures
    ctx.step_latencies_ms["compute_exposure_map"] = latency_ms
    return ctx
