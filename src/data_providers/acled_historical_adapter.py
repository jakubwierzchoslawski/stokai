"""
AcledHistoricalAdapter — HistoricalEventProvider fallback implementation for ACLED.

Calls the ACLED export REST API (https://api.acleddata.com/acled/read) with
ACLED_API_KEY from environment variable. Paginates via page param.
Maps ACLED fields to RawHistoricalEvent with identical shape as GDELT adapter.

Architecture Principle 1: switching from GDELT to ACLED is a SEEDING_PROVIDER=acled
env var change — no code changes required.

Security: ACLED_API_KEY is sourced from env var only; never logged (REQ-N-007 / §12.2).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.data_providers.historical_event_provider import HistoricalEventProvider
from src.ingestion.cold_start.types import RawHistoricalEvent

logger = logging.getLogger(__name__)

ACLED_API_URL = "https://api.acleddata.com/acled/read"
ACLED_PAGE_SIZE = 500

# Fatalities scale: 0 → intensity 1; >= 1000 → intensity 5
FATALITIES_MAX = 1000.0
INTENSITY_MIN = 1.0
INTENSITY_MAX = 5.0


class AcledProviderError(Exception):
    """Domain error for ACLED HTTP or parse failures."""


class AcledHistoricalAdapter(HistoricalEventProvider):
    """Fetches ACLED historical events via paginated REST API.

    Args:
        http_client: injected httpx.AsyncClient (enables mocking in tests).
        api_key: ACLED API key (defaults to ACLED_API_KEY env var if not supplied).
        api_url: override the ACLED API endpoint (for testing).
        page_size: number of records per API page.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        api_url: str = ACLED_API_URL,
        page_size: int = ACLED_PAGE_SIZE,
    ) -> None:
        import os

        self._client = http_client
        self._api_key = api_key or os.environ.get("ACLED_API_KEY", "")
        self._api_url = api_url
        self._page_size = page_size

    def provider_name(self) -> str:
        """Return canonical provider identifier."""
        return "acled"

    def fetch_batches(
        self,
        start_date: date,
        end_date: date,
        batch_size: int = 500,
    ) -> Iterator[list[RawHistoricalEvent]]:
        """Fetch ACLED events in batches within the date range.

        Each yielded list has at most batch_size events. Pagination is handled
        transparently; a single batch may span multiple API pages.
        """
        import asyncio

        return iter(
            asyncio.run(
                self._collect_batches(start_date, end_date, batch_size)
            )
        )

    async def _collect_batches(
        self,
        start_date: date,
        end_date: date,
        batch_size: int,
    ) -> list[list[RawHistoricalEvent]]:
        """Async implementation: return a list of event batches."""
        async with self._get_client() as client:
            all_events = await self._fetch_all_pages(client, start_date, end_date)

        batches: list[list[RawHistoricalEvent]] = []
        current: list[RawHistoricalEvent] = []
        for event in all_events:
            current.append(event)
            if len(current) >= batch_size:
                batches.append(current)
                current = []
        if current:
            batches.append(current)

        logger.info(
            "ACLED: fetched %d events in range %s – %s (%d batches)",
            len(all_events),
            start_date,
            end_date,
            len(batches),
        )
        return batches

    async def _fetch_all_pages(
        self,
        client: httpx.AsyncClient,
        start_date: date,
        end_date: date,
    ) -> list[RawHistoricalEvent]:
        """Paginate through ACLED API until all events are fetched."""
        all_events: list[RawHistoricalEvent] = []
        page = 1

        while True:
            params = {
                "key": self._api_key,  # never logged — see logging below
                "event_date": f"{start_date.isoformat()}|{end_date.isoformat()}",
                "event_date_where": "BETWEEN",
                "limit": self._page_size,
                "page": page,
            }
            logger.debug("Fetching ACLED page %d (key=***redacted***)", page)

            response = await client.get(self._api_url, params=params)
            if response.status_code == 401 or response.status_code == 403:
                raise AcledProviderError(
                    f"ACLED API authentication failed (HTTP {response.status_code}). "
                    "Check ACLED_API_KEY."
                )
            if response.status_code == 404:
                raise AcledProviderError(
                    f"ACLED API endpoint not found (HTTP 404): {self._api_url}"
                )
            response.raise_for_status()

            data = response.json()
            records: list[dict[str, Any]] = data.get("data", [])
            count: int = len(records)

            for record in records:
                event = self._parse_record(record)
                if event is not None:
                    all_events.append(event)

            logger.debug("ACLED page %d: received %d records", page, count)

            # If the page is full, there may be more pages
            if count >= self._page_size:
                page += 1
            else:
                break

        return all_events

    @staticmethod
    def _parse_record(record: dict[str, Any]) -> RawHistoricalEvent | None:
        """Map an ACLED API record to a RawHistoricalEvent.

        Returns None and logs a warning for malformed records.
        """
        try:
            external_id = str(record.get("data_id", "")).strip()
            if not external_id:
                return None

            event_date_str = record.get("event_date", "")
            try:
                occurred_at = datetime.strptime(event_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                logger.warning("ACLED: invalid event_date %r for data_id=%s", event_date_str, external_id)
                return None

            title = str(record.get("event_type", "") or "Unknown event")
            summary = str(record.get("notes", "") or title)

            # Latitude / longitude — may be absent or blank
            lat: float | None = None
            lon: float | None = None
            try:
                lat_val = record.get("latitude")
                if lat_val is not None and lat_val != "":
                    lat = float(lat_val)
            except (TypeError, ValueError):
                pass
            try:
                lon_val = record.get("longitude")
                if lon_val is not None and lon_val != "":
                    lon = float(lon_val)
            except (TypeError, ValueError):
                pass

            # Geo regions from country code
            country = record.get("country", "") or ""
            iso = record.get("iso", "") or ""
            geo_regions = [iso] if iso else ([country] if country else [])

            # Fatalities → intensity_raw [1, 5]
            try:
                fatalities = float(record.get("fatalities", 0) or 0)
            except (TypeError, ValueError):
                fatalities = 0.0

            intensity_raw = _fatalities_to_intensity(fatalities)

            # ACLED uses event type rather than CAMEO codes
            raw_payload: dict[str, Any] = {
                "acled_record": {k: v for k, v in record.items() if k != "key"},
            }

            return RawHistoricalEvent(
                external_id=external_id,
                occurred_at=occurred_at,
                title=title,
                summary=summary,
                lat=lat,
                lon=lon,
                geo_regions=geo_regions,
                cameo_code=None,  # ACLED does not use CAMEO
                intensity_raw=intensity_raw,
                sentiment_raw=0.0,  # ACLED has no sentiment field; default neutral
                source_provider="acled",
                raw_payload=raw_payload,
            )

        except Exception as exc:
            logger.warning("ACLED: failed to parse record: %s — %r", exc, record)
            return None

    def _get_client(self):
        """Return a context manager yielding an httpx.AsyncClient."""
        if self._client is not None:
            return _NoopContextManager(self._client)
        return httpx.AsyncClient(timeout=60.0, follow_redirects=True)


def _fatalities_to_intensity(fatalities: float) -> float:
    """Map fatalities [0, ∞) → intensity_raw [1.0, 5.0].

    0 fatalities → 1.0 (minimum)
    >= 1000 fatalities → 5.0 (maximum)
    Linear in between.
    """
    capped = min(fatalities, FATALITIES_MAX)
    return INTENSITY_MIN + (capped / FATALITIES_MAX) * (INTENSITY_MAX - INTENSITY_MIN)


class _NoopContextManager:
    """Wraps an already-open client so it can be used as an async context manager."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: Any) -> None:
        pass
