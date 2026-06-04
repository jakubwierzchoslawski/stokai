"""
Unit tests for AcledHistoricalAdapter.

All HTTP calls are mocked. Tests verify field mapping, fatalities normalization,
provider name, missing field handling, and pagination.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.data_providers.acled_historical_adapter import (
    AcledHistoricalAdapter,
    _fatalities_to_intensity,
)
from src.ingestion.cold_start.types import RawHistoricalEvent


# ─── Helpers ────────────────────────────────────────────────────────────────

def _acled_record(
    data_id="1001",
    event_date="1979-01-15",
    event_type="Violence against civilians",
    notes="Rebels attacked a village.",
    latitude="3.8",
    longitude="11.5",
    country="Cameroon",
    iso="CMR",
    fatalities="5",
) -> dict:
    return {
        "data_id": data_id,
        "event_date": event_date,
        "event_type": event_type,
        "notes": notes,
        "latitude": latitude,
        "longitude": longitude,
        "country": country,
        "iso": iso,
        "fatalities": fatalities,
    }


def _make_mock_client(pages: list[list[dict]]) -> httpx.AsyncClient:
    """Build a mock httpx client that returns paginated ACLED responses."""
    call_count = [0]

    async def mock_get(url, params=None, **kwargs):
        idx = call_count[0]
        page_data = pages[idx] if idx < len(pages) else []
        call_count[0] += 1

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"data": page_data, "count": len(page_data)}
        return resp

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=mock_get)
    return client


# ─── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFatalitiesToIntensity:
    """Verify fatalities → intensity normalization."""

    def test_zero_fatalities_maps_to_intensity_1(self):
        assert _fatalities_to_intensity(0) == pytest.approx(1.0)

    def test_1000_fatalities_maps_to_intensity_5(self):
        assert _fatalities_to_intensity(1000) == pytest.approx(5.0)

    def test_over_1000_fatalities_capped_at_5(self):
        assert _fatalities_to_intensity(5000) == pytest.approx(5.0)

    def test_500_fatalities_maps_to_intensity_3(self):
        assert _fatalities_to_intensity(500) == pytest.approx(3.0)


@pytest.mark.unit
class TestProviderName:
    def test_provider_name_returns_acled(self):
        adapter = AcledHistoricalAdapter(api_key="test")
        assert adapter.provider_name() == "acled"


@pytest.mark.unit
class TestFetchBatchesMapping:
    """Test that fetch_batches maps ACLED fields to RawHistoricalEvent correctly."""

    @pytest.mark.asyncio
    async def test_maps_acled_fields_to_raw_historical_event(self):
        """fetch_batches with mock client maps ACLED response fields correctly."""
        record = _acled_record(
            data_id="1001",
            event_date="1979-01-15",
            event_type="Protests",
            notes="Students protested.",
            latitude="5.0",
            longitude="10.0",
            country="Nigeria",
            iso="NGA",
            fatalities="0",
        )
        client = _make_mock_client([[record]])  # one page with one record
        adapter = AcledHistoricalAdapter(http_client=client, api_key="test", page_size=500)

        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )

        all_events = [e for batch in batches for e in batch]
        assert len(all_events) == 1
        event = all_events[0]
        assert isinstance(event, RawHistoricalEvent)
        assert event.external_id == "1001"
        assert event.source_provider == "acled"
        assert event.title == "Protests"
        assert event.summary == "Students protested."
        assert event.lat == pytest.approx(5.0)
        assert event.lon == pytest.approx(10.0)
        assert event.geo_regions == ["NGA"]
        assert event.cameo_code is None
        assert event.occurred_at.year == 1979

    @pytest.mark.asyncio
    async def test_missing_latitude_produces_lat_none_without_raising(self):
        """Missing latitude produces lat=None without raising."""
        record = _acled_record(latitude=None, longitude=None)
        client = _make_mock_client([[record]])
        adapter = AcledHistoricalAdapter(http_client=client, api_key="test", page_size=500)

        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )
        all_events = [e for batch in batches for e in batch]
        assert len(all_events) == 1
        assert all_events[0].lat is None
        assert all_events[0].lon is None

    @pytest.mark.asyncio
    async def test_zero_fatalities_produces_intensity_1(self):
        """fatalities=0 → intensity_raw=1.0."""
        record = _acled_record(fatalities="0")
        client = _make_mock_client([[record]])
        adapter = AcledHistoricalAdapter(http_client=client, api_key="test", page_size=500)

        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )
        events = [e for b in batches for e in b]
        assert events[0].intensity_raw == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_1000_fatalities_produces_intensity_5(self):
        """fatalities >= 1000 → intensity_raw=5.0."""
        record = _acled_record(fatalities="1000")
        client = _make_mock_client([[record]])
        adapter = AcledHistoricalAdapter(http_client=client, api_key="test", page_size=500)

        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )
        events = [e for b in batches for e in b]
        assert events[0].intensity_raw == pytest.approx(5.0)


@pytest.mark.unit
class TestPagination:
    """Verify pagination: when API returns count == page_size, fetch next page."""

    @pytest.mark.asyncio
    async def test_pagination_fetches_all_pages(self):
        """When API returns count == page_size, the adapter fetches the next page."""
        page_size = 2
        page1 = [_acled_record(data_id="1"), _acled_record(data_id="2")]
        page2 = [_acled_record(data_id="3")]  # Only 1 record → last page
        client = _make_mock_client([page1, page2])
        adapter = AcledHistoricalAdapter(http_client=client, api_key="test", page_size=page_size)

        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )
        all_events = [e for batch in batches for e in batch]
        assert len(all_events) == 3
        ids = {e.external_id for e in all_events}
        assert ids == {"1", "2", "3"}

    @pytest.mark.asyncio
    async def test_single_page_not_full_stops_pagination(self):
        """When API returns count < page_size, no further pages are fetched."""
        page_size = 10
        page1 = [_acled_record(data_id=str(i)) for i in range(5)]  # 5 < 10 → stop
        client = _make_mock_client([page1])
        adapter = AcledHistoricalAdapter(http_client=client, api_key="test", page_size=page_size)

        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )
        all_events = [e for batch in batches for e in batch]
        assert len(all_events) == 5
        # Client was only called once
        assert client.get.call_count == 1
