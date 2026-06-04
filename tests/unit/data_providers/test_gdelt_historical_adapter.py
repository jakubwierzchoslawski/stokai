"""
Unit tests for GdeltHistoricalAdapter.

All HTTP calls are mocked using httpx.MockTransport so no network is required.
Tests verify field mapping, normalization, date filtering, error handling, and
CSV parsing robustness.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.data_providers.gdelt_historical_adapter import (
    GdeltHistoricalAdapter,
    GdeltProviderError,
    _linear_scale,
)
from src.ingestion.cold_start.types import RawHistoricalEvent


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_gdelt_row(
    event_id="123456",
    sql_date="19790115",
    actor1="USA",
    actor2="RUS",
    cameo="190",
    goldstein="5.0",
    avg_tone="-20.0",
    lat="40.0",
    lon="-74.0",
    country_code="US",
) -> list[str]:
    """Build a minimal GDELT v2 TSV row with 60 columns."""
    row = [""] * 60
    row[0] = event_id
    row[1] = sql_date
    row[5] = actor1
    row[11] = actor2
    row[28] = cameo
    row[30] = goldstein
    row[34] = lat
    row[35] = lon
    row[37] = country_code
    row[53] = avg_tone
    return row


def _make_zip_csv(rows: list[list[str]]) -> bytes:
    """Create an in-memory ZIP containing a TSV file."""
    tsv_lines = "\n".join("\t".join(r) for r in rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("events.CSV", tsv_lines)
    return buf.getvalue()


def _make_master_list(file_date: str = "19790115", base_url: str = "http://test.example") -> str:
    """Create a fake GDELT master file list line."""
    # Format: <size> <md5> <url>
    filename = f"{file_date}000000.export.CSV.zip"
    return f"1000 abc123 {base_url}/{filename}\n"


def _make_mock_client(master_text: str, zip_data: bytes) -> httpx.AsyncClient:
    """Build a mock httpx client that returns master list and a ZIP download."""
    responses = {}

    async def mock_get(url, **kwargs):
        if "masterfile" in url or "index" in url:
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 200
            resp.text = master_text
            resp.raise_for_status = MagicMock()
            return resp
        else:
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 200
            resp.content = zip_data
            resp.raise_for_status = MagicMock()
            return resp

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=mock_get)
    return client


# ─── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGoldsteinScaleNormalization:
    """Verify GoldsteinScale → intensity_raw mapping."""

    def test_goldstein_minus10_maps_to_intensity_1(self):
        result = _linear_scale(-10.0, -10.0, 10.0, 1.0, 5.0)
        assert result == pytest.approx(1.0)

    def test_goldstein_plus10_maps_to_intensity_5(self):
        result = _linear_scale(10.0, -10.0, 10.0, 1.0, 5.0)
        assert result == pytest.approx(5.0)

    def test_goldstein_zero_maps_to_intensity_3(self):
        result = _linear_scale(0.0, -10.0, 10.0, 1.0, 5.0)
        assert result == pytest.approx(3.0)


@pytest.mark.unit
class TestAvgToneNormalization:
    """Verify AvgTone → sentiment_raw mapping."""

    def test_avg_tone_minus100_maps_to_sentiment_minus1(self):
        result = _linear_scale(-100.0, -100.0, 100.0, -1.0, 1.0)
        assert result == pytest.approx(-1.0)

    def test_avg_tone_plus100_maps_to_sentiment_plus1(self):
        result = _linear_scale(100.0, -100.0, 100.0, -1.0, 1.0)
        assert result == pytest.approx(1.0)

    def test_avg_tone_zero_maps_to_sentiment_zero(self):
        result = _linear_scale(0.0, -100.0, 100.0, -1.0, 1.0)
        assert result == pytest.approx(0.0)


@pytest.mark.unit
class TestFetchBatchesMapping:
    """Test that fetch_batches maps GDELT rows to RawHistoricalEvent correctly."""

    @pytest.mark.asyncio
    async def test_fetch_batches_returns_raw_historical_events(self):
        """fetch_batches with mock HTTP client returns expected RawHistoricalEvent objects."""
        rows = [
            _make_gdelt_row(
                event_id="999",
                sql_date="19790115",
                actor1="USA",
                actor2="RUS",
                cameo="190",
                goldstein="5.0",
                avg_tone="-20.0",
                lat="40.0",
                lon="-74.0",
                country_code="US",
            )
        ]
        zip_data = _make_zip_csv(rows)
        master = _make_master_list("19790115", "http://test.example")
        client = _make_mock_client(master, zip_data)

        adapter = GdeltHistoricalAdapter(http_client=client)
        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )

        assert len(batches) >= 1
        events = [e for batch in batches for e in batch]
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, RawHistoricalEvent)
        assert event.external_id == "999"
        assert event.source_provider == "gdelt"
        assert event.cameo_code == "190"
        assert event.geo_regions == ["US"]
        assert event.occurred_at.year == 1979

    @pytest.mark.asyncio
    async def test_date_filter_skips_files_outside_range(self):
        """Files outside start_date–end_date are not downloaded."""
        # File date 19800115 is outside range [1979-01-01, 1979-12-31]
        rows = [_make_gdelt_row(event_id="X", sql_date="19800115")]
        zip_data = _make_zip_csv(rows)
        master = _make_master_list("19800115", "http://test.example")
        client = _make_mock_client(master, zip_data)

        adapter = GdeltHistoricalAdapter(http_client=client)
        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )

        # No files should be downloaded; no events returned
        all_events = [e for batch in batches for e in batch]
        assert len(all_events) == 0


@pytest.mark.unit
class TestHttp404Handling:
    """Verify HTTP 404 raises GdeltProviderError (not raw httpx error)."""

    @pytest.mark.asyncio
    async def test_http_404_on_file_raises_domain_error(self):
        """HTTP 404 on a specific GDELT file raises GdeltProviderError."""
        async def mock_get(url, **kwargs):
            if "masterfile" in url or "index" in url:
                resp = MagicMock(spec=httpx.Response)
                resp.status_code = 200
                resp.text = _make_master_list("19790115", "http://test.example")
                resp.raise_for_status = MagicMock()
                return resp
            else:
                # File returns 404
                resp = MagicMock(spec=httpx.Response)
                resp.status_code = 404
                resp.raise_for_status = MagicMock()
                return resp

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=mock_get)

        adapter = GdeltHistoricalAdapter(http_client=client)
        with pytest.raises(GdeltProviderError, match="404"):
            await adapter._collect_batches(
                start_date=date(1979, 1, 1),
                end_date=date(1979, 12, 31),
                batch_size=500,
            )


@pytest.mark.unit
class TestMalformedRowHandling:
    """Verify malformed rows are skipped while valid rows are still returned."""

    @pytest.mark.asyncio
    async def test_malformed_rows_skipped_valid_rows_returned(self):
        """Malformed CSV rows are logged and skipped; valid rows still returned."""
        valid_row = _make_gdelt_row(event_id="111", sql_date="19790115")
        malformed_row = ["too", "few", "columns"]  # Only 3 columns

        zip_data = _make_zip_csv([malformed_row, valid_row])
        master = _make_master_list("19790115", "http://test.example")
        client = _make_mock_client(master, zip_data)

        adapter = GdeltHistoricalAdapter(http_client=client)
        batches = await adapter._collect_batches(
            start_date=date(1979, 1, 1),
            end_date=date(1979, 12, 31),
            batch_size=500,
        )

        all_events = [e for batch in batches for e in batch]
        # Only the valid row should be parsed
        assert len(all_events) == 1
        assert all_events[0].external_id == "111"


@pytest.mark.unit
class TestProviderName:
    """Verify provider_name() returns 'gdelt'."""

    def test_provider_name_returns_gdelt(self):
        adapter = GdeltHistoricalAdapter()
        assert adapter.provider_name() == "gdelt"
