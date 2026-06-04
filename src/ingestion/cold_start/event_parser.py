"""
EventParser — transforms RawHistoricalEvent into a GeoEventCreate domain model.

Responsibilities:
- Clamp intensity_raw and sentiment_raw to valid ranges.
- Derive category list from CAMEO root code.
- Produce a deterministic UUID5 event_id for idempotency across re-runs.
- Set seeding-time metadata (detected_at, tenant_id).

This module has no I/O — pure transformation logic.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from src.ingestion.cold_start.types import RawHistoricalEvent

logger = logging.getLogger(__name__)

# UUID namespace for deterministic event_id generation (UUID5)
# Using a stable custom namespace UUID so event_ids are reproducible across runs.
_EVENT_ID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace

# ─── CAMEO root-code to category mapping ─────────────────────────────────────
# Based on CAMEO codebook root codes (first two digits of EventCode).
# Reference: http://data.gdeltproject.org/documentation/CAMEO.Manual.1.1b3.pdf
_CAMEO_CATEGORY_MAP: dict[str, str] = {
    "01": "VERBAL_COOPERATION",    # Make public statement
    "02": "VERBAL_COOPERATION",    # Appeal
    "03": "VERBAL_COOPERATION",    # Express intent to cooperate
    "04": "VERBAL_COOPERATION",    # Consult
    "05": "VERBAL_COOPERATION",    # Engage in diplomatic cooperation
    "06": "MATERIAL_COOPERATION",  # Engage in material cooperation
    "07": "MATERIAL_COOPERATION",  # Provide aid
    "08": "MATERIAL_COOPERATION",  # Yield
    "09": "VERBAL_CONFLICT",       # Investigate
    "10": "VERBAL_COOPERATION",    # Demand
    "11": "VERBAL_CONFLICT",       # Disapprove
    "12": "VERBAL_CONFLICT",       # Reject
    "13": "VERBAL_CONFLICT",       # Threaten
    "14": "PROTEST",               # Protest
    "15": "ARMED_CONFLICT",        # Exhibit military posture
    "16": "ARMED_CONFLICT",        # Reduce relations
    "17": "VERBAL_CONFLICT",       # Coerce
    "18": "ARMED_CONFLICT",        # Assault
    "19": "ARMED_CONFLICT",        # Fight
    "20": "ARMED_CONFLICT",        # Use unconventional mass violence
}


@dataclass
class GeoEventCreate:
    """Data transfer object for inserting a new geo_event row.

    Matches the geo_event table schema (Architecture §10).
    All fields required for a cold-start seed insert.
    """

    event_id: UUID
    occurred_at: datetime
    detected_at: datetime
    category: list[str]
    intensity: int            # 1–5 (clamped, integer)
    title: str
    summary: str
    lat: float | None
    lon: float | None
    geo_regions: list[str]
    affected_sectors: list[str]
    sentiment: float          # [-1.0, 1.0]
    cameo_code: str | None
    source_provider: str
    tenant_id: UUID | None    # NULL for global (shared) seeded events
    ttl: None = field(default=None)  # Always None (infinite TTL, REQ-N-011)
    raw_payload: dict = field(default_factory=dict)


def parse_raw_event(raw: RawHistoricalEvent, tenant_id: UUID | None = None) -> GeoEventCreate:
    """Transform a RawHistoricalEvent into a GeoEventCreate domain object.

    Args:
        raw: Provider-normalized event from GdeltHistoricalAdapter or AcledHistoricalAdapter.
        tenant_id: Tenant scope for the event. None for global/shared seeded events.

    Returns:
        GeoEventCreate ready for insertion via GeoEventRepository.
    """
    event_id = _derive_event_id(raw.source_provider, raw.external_id)
    intensity = _clamp_intensity(raw.intensity_raw)
    sentiment = _clamp_sentiment(raw.sentiment_raw)
    category = _cameo_to_categories(raw.cameo_code)

    return GeoEventCreate(
        event_id=event_id,
        occurred_at=raw.occurred_at,
        detected_at=datetime.now(tz=timezone.utc),
        category=category,
        intensity=intensity,
        title=raw.title,
        summary=raw.summary,
        lat=raw.lat,
        lon=raw.lon,
        geo_regions=raw.geo_regions,
        affected_sectors=[],  # Mode A LLM step — not available during cold-start
        sentiment=sentiment,
        cameo_code=raw.cameo_code,
        source_provider=raw.source_provider,
        tenant_id=tenant_id,
        ttl=None,  # Infinite TTL per REQ-N-011
        raw_payload=raw.raw_payload,
    )


def _derive_event_id(source_provider: str, external_id: str) -> UUID:
    """Produce a deterministic UUID5 from (source_provider, external_id).

    Using UUID5 (SHA-1 based) ensures the same input always yields the same
    UUID, enabling idempotent re-runs of the seeding pipeline.
    """
    name = f"{source_provider}:{external_id}"
    return uuid.uuid5(_EVENT_ID_NAMESPACE, name)


def _clamp_intensity(raw: float) -> int:
    """Clamp and round intensity_raw to integer [1, 5]."""
    clamped = max(1.0, min(5.0, raw))
    return int(round(clamped))


def _clamp_sentiment(raw: float) -> float:
    """Clamp sentiment_raw to float [-1.0, 1.0]."""
    return max(-1.0, min(1.0, raw))


def _cameo_to_categories(cameo_code: str | None) -> list[str]:
    """Map a CAMEO event code to one or more category strings.

    Uses the first two digits (root code) for the lookup.
    Returns ['UNKNOWN'] if the code is absent or unrecognised.
    """
    if not cameo_code:
        return ["UNKNOWN"]

    # Root code: first two digits
    root = cameo_code[:2].lstrip("0") or "0"
    root_padded = cameo_code[:2]  # zero-padded for map lookup

    category = _CAMEO_CATEGORY_MAP.get(root_padded)
    if category is None:
        # Try with zero-padded single digit → root '01' etc.
        try:
            root_int = int(cameo_code[:3]) // 10  # e.g. 190 → 19
            lookup = str(root_int).zfill(2)
            category = _CAMEO_CATEGORY_MAP.get(lookup)
        except (ValueError, IndexError):
            category = None

    if category is None:
        logger.debug("Unknown CAMEO root code %r → UNKNOWN", cameo_code[:2])
        return ["UNKNOWN"]

    return [category]
