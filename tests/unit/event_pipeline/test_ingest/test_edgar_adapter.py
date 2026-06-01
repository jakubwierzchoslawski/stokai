"""Unit tests for EdgarAdapter (TASK-003, TDD).

Tests written before implementation.
Covers: AC-001, AC-002, AC-003.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_pipeline.pipeline_state import RawEventSource


class TestEdgarAdapterParseWebhookProducesPayload:
    """test_edgar_adapter_parse_webhook_produces_payload"""

    def test_edgar_adapter_parse_webhook_produces_payload(self):
        """EdgarAdapter.parse_webhook produces RawEventPayload from EDGAR body."""
        from src.event_pipeline.ingest.edgar_adapter import EdgarAdapter
        from src.event_pipeline.pipeline_state import RawEventPayload

        tenant_id = uuid.uuid4()

        # Simulated EDGAR ATOM-style entry body
        body = {
            "title": "10-K filing by AAPL",
            "link": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
            "updated": "2026-06-01T12:00:00Z",
            "summary": "Annual report filed by Apple Inc.",
            "category": "10-K",
            "companyName": "Apple Inc.",
            "cikNumber": "320193",
            "filingDate": "2026-06-01",
        }

        adapter = EdgarAdapter(tenant_id=tenant_id)
        payload = adapter.parse_webhook(body)

        assert isinstance(payload, RawEventPayload)
        assert payload.source == RawEventSource.SEC_EDGAR
        assert payload.tenant_id == tenant_id
        assert payload.raw_payload["title"] == "10-K filing by AAPL"
