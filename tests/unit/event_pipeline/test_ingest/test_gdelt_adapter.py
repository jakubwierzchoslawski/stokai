"""Unit tests for GdeltAdapter (TASK-003, TDD).

Tests written before implementation.
Covers: AC-001, AC-002, AC-003.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_pipeline.pipeline_state import RawEventSource


class TestGdeltAdapterParsesValidResponse:
    """test_gdelt_adapter_parses_valid_response"""

    @pytest.mark.asyncio
    async def test_gdelt_adapter_parses_valid_response(self):
        """GdeltAdapter returns a list of RawEventPayload from a valid API response."""
        from src.event_pipeline.ingest.gdelt_adapter import GdeltAdapter
        from src.event_pipeline.pipeline_state import RawEventPayload

        tenant_id = uuid.uuid4()
        fake_response = {
            "articles": [
                {
                    "title": "Conflict erupts in region X",
                    "url": "https://example.com/1",
                    "seendate": "20260601T120000Z",
                    "sourceurl": "https://example.com",
                    "tone": "-5.0",
                    "actor1geo_lat": "40.7128",
                    "actor1geo_long": "-74.0060",
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = fake_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            adapter = GdeltAdapter(tenant_id=tenant_id)
            payloads = await adapter.poll()

        assert len(payloads) == 1
        payload = payloads[0]
        assert isinstance(payload, RawEventPayload)
        assert payload.source == RawEventSource.GDELT
        assert payload.tenant_id == tenant_id
        assert isinstance(payload.detected_at, datetime)
        assert "title" in payload.raw_payload


class TestGdeltAdapterWrapsHttpError:
    """test_gdelt_adapter_wraps_http_error"""

    @pytest.mark.asyncio
    async def test_gdelt_adapter_wraps_http_error(self):
        """GdeltAdapter raises ProviderUnavailableError on HTTP 503."""
        from src.event_pipeline.ingest.gdelt_adapter import GdeltAdapter
        from src.event_pipeline.ingest.exceptions import ProviderUnavailableError
        import httpx

        tenant_id = uuid.uuid4()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "503",
                    request=MagicMock(),
                    response=MagicMock(status_code=503),
                )
            )
            mock_client_class.return_value = mock_client

            adapter = GdeltAdapter(tenant_id=tenant_id)
            with pytest.raises(ProviderUnavailableError):
                await adapter.poll()
