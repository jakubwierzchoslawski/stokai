"""GdeltEventInjector — builds GDELT geo-event payloads for performance tests.

PLAN-N-001 TASK-001.

Each call to build_payload(index) produces a distinct GDELT payload with
varied lat/lon coordinates and category fields to prevent deduplication
from collapsing the test run.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from src.event_pipeline.pipeline_state import RawEventPayload, RawEventSource

# Stable test tenant ID (shared across all performance injectors).
_PERF_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Realistic geo-event categories used in GDELT data.
_GDELT_CATEGORIES = [
    "CONFLICT",
    "PROTEST",
    "DISASTER",
    "ELECTION",
    "ECONOMIC",
    "DIPLOMACY",
]

# Geo coordinate grid — varied per index to ensure uniqueness.
_BASE_COORDINATES = [
    (40.7128, -74.0060),   # New York
    (51.5074, -0.1278),    # London
    (35.6762, 139.6503),   # Tokyo
    (48.8566, 2.3522),     # Paris
    (55.7558, 37.6176),    # Moscow
    (-33.8688, 151.2093),  # Sydney
    (19.4326, -99.1332),   # Mexico City
    (28.6139, 77.2090),    # New Delhi
    (1.3521, 103.8198),    # Singapore
    (-23.5505, -46.6333),  # São Paulo
]


class GdeltEventInjector:
    """Builds GDELT ``RawEventPayload`` instances for latency tests.

    Implements the ``EventInjector`` Protocol.

    Each ``build_payload(index)`` call varies the geographic coordinates,
    category, and a unique event ID to guarantee deduplication-safe payloads.

    SRP: single responsibility — builds GDELT geo-event payloads only.
    """

    source_type: str = "GDELT"

    def build_payload(self, index: int) -> RawEventPayload:
        """Build a distinct GDELT payload for the given run index.

        Parameters
        ----------
        index:
            Zero-based run counter.  Coordinates and category rotate per index;
            a unique event_id is generated per call.

        Returns
        -------
        RawEventPayload:
            Fully-populated GDELT payload with detected_at set to now().
        """
        coord_pair = _BASE_COORDINATES[index % len(_BASE_COORDINATES)]
        lat = coord_pair[0] + (index * 0.01)   # small offset to ensure uniqueness
        lon = coord_pair[1] + (index * 0.01)
        category = _GDELT_CATEGORIES[index % len(_GDELT_CATEGORIES)]

        raw_payload = {
            "event_id": f"gdelt-perf-{index:06d}-{uuid.uuid4().hex[:8]}",
            "lat": lat,
            "lon": lon,
            "category": category,
            "goldstein_scale": round(-5.0 + (index % 100) * 0.1, 2),
            "num_mentions": 10 + (index % 200),
            "num_sources": 1 + (index % 20),
            "event_date": datetime.utcnow().strftime("%Y%m%d"),
            "actor1": f"COUNTRY_{index % 50:02d}",
            "actor2": f"COUNTRY_{(index + 7) % 50:02d}",
            "action_geo_fullname": f"PerfRegion_{index % 30}",
            "run_index": index,
        }

        return RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload=raw_payload,
            detected_at=datetime.utcnow(),
            tenant_id=_PERF_TENANT_ID,
        )
