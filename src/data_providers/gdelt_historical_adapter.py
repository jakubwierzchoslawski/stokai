"""
GdeltHistoricalAdapter — HistoricalEventProvider implementation for GDELT.

Downloads GDELT master file list, filters by date range, streams monthly
ZIP archives, and parses each row into a RawHistoricalEvent.

Architecture Principle 1: this is the only module that contacts the GDELT HTTP API.
All I/O is via httpx async client (REQ-N-007 — no SDK, pure HTTP).
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import zipfile
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import Any

import httpx

from src.data_providers.historical_event_provider import HistoricalEventProvider
from src.ingestion.cold_start.types import RawHistoricalEvent

logger = logging.getLogger(__name__)

# GDELT master file list for GDELTv2 (April 2015 – present)
GDELT_V2_MASTER_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
# GDELT v1 master file list (1979 – 2013, quarterly then daily)
GDELT_V1_MASTER_URL = "http://data.gdeltproject.org/events/index.csv"

# GoldsteinScale range is [-10, +10]; map to intensity [1, 5]
GOLDSTEIN_MIN = -10.0
GOLDSTEIN_MAX = 10.0
INTENSITY_MIN = 1.0
INTENSITY_MAX = 5.0

# AvgTone range can exceed [-100, +100] but we clamp there
AVG_TONE_MIN = -100.0
AVG_TONE_MAX = 100.0


class GdeltProviderError(Exception):
    """Domain error for GDELT HTTP or parse failures."""


class GdeltHistoricalAdapter(HistoricalEventProvider):
    """Streams GDELT v2 historical events in monthly batches.

    Args:
        http_client: injected httpx.AsyncClient (enables mocking in tests).
        master_url: override the GDELT master file URL (for testing).
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        master_url: str = GDELT_V2_MASTER_URL,
    ) -> None:
        self._client = http_client
        self._master_url = master_url
        self._owns_client = http_client is None

    def provider_name(self) -> str:
        """Return canonical provider identifier."""
        return "gdelt"

    def fetch_batches(
        self,
        start_date: date,
        end_date: date,
        batch_size: int = 500,
    ) -> Iterator[list[RawHistoricalEvent]]:
        """Fetch GDELT events in monthly batches within the date range.

        Runs the async implementation via asyncio.run() so the method is
        synchronous (matches the Iterator protocol). Callers needing full async
        control can await _fetch_batches_async() directly.
        """
        return asyncio.run(
            self._collect_batches(start_date, end_date, batch_size)
        )

    async def _collect_batches(
        self,
        start_date: date,
        end_date: date,
        batch_size: int,
    ) -> list[list[RawHistoricalEvent]]:
        """Async implementation: returns a list of event batches."""
        async with self._get_client() as client:
            file_urls = await self._fetch_file_urls(client, start_date, end_date)
            logger.info(
                "GDELT: found %d file URLs in range %s – %s",
                len(file_urls),
                start_date,
                end_date,
            )
            batches = []
            current_batch: list[RawHistoricalEvent] = []

            for url in file_urls:
                try:
                    events = await self._download_and_parse(client, url)
                    for event in events:
                        current_batch.append(event)
                        if len(current_batch) >= batch_size:
                            batches.append(current_batch)
                            current_batch = []
                except GdeltProviderError as exc:
                    logger.warning("Skipping GDELT file %s: %s", url, exc)
                    raise  # propagate for callers to handle

            if current_batch:
                batches.append(current_batch)

            return batches

    async def _fetch_file_urls(
        self,
        client: httpx.AsyncClient,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """Download master file list and return URLs within the date range."""
        logger.info("Fetching GDELT master file list from %s", self._master_url)
        response = await client.get(self._master_url)
        if response.status_code == 404:
            raise GdeltProviderError(
                f"GDELT master file list returned 404: {self._master_url}"
            )
        response.raise_for_status()

        urls: list[str] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Master list format: "<size> <md5> <url>"
            parts = line.split()
            if len(parts) >= 3:
                url = parts[2]
            elif len(parts) == 1:
                url = parts[0]
            else:
                continue

            # Extract date from URL — GDELT v2 filenames: YYYYMMDDHHMMSS.export.CSV.zip
            file_date = self._extract_date_from_url(url)
            if file_date is None:
                continue
            if start_date <= file_date <= end_date:
                urls.append(url)

        return urls

    @staticmethod
    def _extract_date_from_url(url: str) -> date | None:
        """Extract the date portion from a GDELT file URL."""
        try:
            filename = url.rsplit("/", 1)[-1]
            # GDELT v2: YYYYMMDDHHMMSS.export.CSV.zip → first 8 chars are YYYYMMDD
            date_str = filename[:8]
            return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        except (ValueError, IndexError):
            return None

    async def _download_and_parse(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> list[RawHistoricalEvent]:
        """Download a GDELT ZIP, extract the CSV, and parse rows."""
        logger.debug("Downloading GDELT file: %s", url)
        response = await client.get(url)
        if response.status_code == 404:
            raise GdeltProviderError(f"GDELT file not found (HTTP 404): {url}")
        response.raise_for_status()

        events: list[RawHistoricalEvent] = []
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".CSV") or n.endswith(".csv")]
                if not csv_names:
                    logger.warning("No CSV found in GDELT ZIP: %s", url)
                    return events
                with zf.open(csv_names[0]) as csv_file:
                    reader = csv.reader(
                        io.TextIOWrapper(csv_file, encoding="utf-8", errors="replace"),
                        delimiter="\t",
                    )
                    for row in reader:
                        event = self._parse_row(row, url)
                        if event is not None:
                            events.append(event)
        except zipfile.BadZipFile as exc:
            logger.warning("Malformed ZIP from GDELT (%s): %s", url, exc)

        return events

    @staticmethod
    def _parse_row(row: list[str], source_url: str) -> RawHistoricalEvent | None:
        """Parse a GDELT TSV row into a RawHistoricalEvent.

        Returns None and logs a warning for malformed rows.

        GDELT v2 column indices (0-based):
            0   GLOBALEVENTID
            1   SQLDATE           YYYYMMDD
            5   Actor1Name
            11  Actor2Name
            28  EventCode         CAMEO code
            30  GoldsteinScale    [-10,+10]
            34  Actor1Geo_Lat
            35  Actor1Geo_Long
            53  AvgTone           usually [-100,+100]
        """
        try:
            if len(row) < 57:
                logger.debug("GDELT row too short (%d cols), skipping", len(row))
                return None

            external_id = row[0].strip()
            if not external_id:
                return None

            # Parse occurred_at from SQLDATE (YYYYMMDD)
            sql_date = row[1].strip()
            if len(sql_date) != 8:
                logger.debug("Unexpected SQLDATE format: %r, skipping", sql_date)
                return None
            occurred_at = datetime(
                int(sql_date[:4]),
                int(sql_date[4:6]),
                int(sql_date[6:8]),
                tzinfo=timezone.utc,
            )

            actor1 = row[5].strip()
            actor2 = row[11].strip()
            cameo_code = row[28].strip() or None
            title = f"{actor1} — {actor2}" if actor2 else actor1 or "Unknown actors"

            goldstein_str = row[30].strip()
            avg_tone_str = row[53].strip() if len(row) > 53 else ""

            goldstein = float(goldstein_str) if goldstein_str else 0.0
            avg_tone = float(avg_tone_str) if avg_tone_str else 0.0

            # Normalize GoldsteinScale [-10,+10] → intensity_raw [1.0, 5.0]
            intensity_raw = _linear_scale(
                goldstein, GOLDSTEIN_MIN, GOLDSTEIN_MAX, INTENSITY_MIN, INTENSITY_MAX
            )

            # Normalize AvgTone [-100,+100] → sentiment_raw [-1.0, +1.0]
            sentiment_raw = _linear_scale(
                avg_tone, AVG_TONE_MIN, AVG_TONE_MAX, -1.0, 1.0
            )

            lat: float | None = None
            lon: float | None = None
            try:
                lat_str = row[34].strip()
                lon_str = row[35].strip()
                if lat_str:
                    lat = float(lat_str)
                if lon_str:
                    lon = float(lon_str)
            except (ValueError, IndexError):
                pass

            # Country code: Actor1Geo_CountryCode at index 37
            geo_regions: list[str] = []
            try:
                country_code = row[37].strip()
                if country_code:
                    geo_regions = [country_code]
            except IndexError:
                pass

            raw_payload: dict[str, Any] = {
                "source_url": source_url,
                "row_index": external_id,
                "raw_columns": row[:60],  # store first 60 cols for audit
            }

            return RawHistoricalEvent(
                external_id=external_id,
                occurred_at=occurred_at,
                title=title,
                summary=title,  # GDELT has no narrative text; title doubles as summary
                lat=lat,
                lon=lon,
                geo_regions=geo_regions,
                cameo_code=cameo_code,
                intensity_raw=intensity_raw,
                sentiment_raw=sentiment_raw,
                source_provider="gdelt",
                raw_payload=raw_payload,
            )

        except (ValueError, IndexError) as exc:
            logger.warning("Malformed GDELT row (skipping): %s — row: %r", exc, row[:10])
            return None

    def _get_client(self):
        """Return a context manager yielding an httpx.AsyncClient."""
        if self._client is not None:
            return _NoopContextManager(self._client)
        return httpx.AsyncClient(timeout=120.0, follow_redirects=True)


def _linear_scale(
    value: float,
    src_min: float,
    src_max: float,
    dst_min: float,
    dst_max: float,
) -> float:
    """Linearly map value from [src_min, src_max] to [dst_min, dst_max].

    Clamps the result to [dst_min, dst_max].
    """
    if src_max == src_min:
        return (dst_min + dst_max) / 2.0
    normalized = (value - src_min) / (src_max - src_min)
    scaled = dst_min + normalized * (dst_max - dst_min)
    return max(dst_min, min(dst_max, scaled))


class _NoopContextManager:
    """Wraps an already-open client so it can be used as an async context manager."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: Any) -> None:
        pass
