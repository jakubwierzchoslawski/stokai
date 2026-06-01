"""Shared fixtures for event_pipeline integration tests.

These tests require:
- A real PostgreSQL test DB with pgvector extension enabled.
- A real Redis instance.
Both are expected to be available via environment variables or docker-compose.test.yml.
LLM calls are replaced with deterministic mock responses.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.pipeline_state import (
    AlertRoute,
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


# ---------------------------------------------------------------------------
# Fake adapters for integration tests
# ---------------------------------------------------------------------------

class FakeGdeltAdapter:
    """Returns a fixed RawEventPayload for GDELT in integration tests."""

    source = RawEventSource.GDELT.value

    def __init__(self, tenant_id: uuid.UUID) -> None:
        self._tenant_id = tenant_id

    def poll(self) -> list[RawEventPayload]:
        return [
            RawEventPayload(
                source=RawEventSource.GDELT,
                raw_payload={
                    "title": "Integration test conflict event",
                    "url": "https://example.com/test",
                    "actor1geo_lat": "51.5",
                    "actor1geo_long": "-0.1",
                },
                detected_at=datetime.now(timezone.utc),
                tenant_id=self._tenant_id,
            )
        ]

    def parse_webhook(self, body: dict) -> RawEventPayload:
        return self.poll()[0]


class FakeEdgarAdapter:
    """Returns a fixed RawEventPayload for EDGAR in integration tests."""

    source = RawEventSource.SEC_EDGAR.value

    def __init__(self, tenant_id: uuid.UUID) -> None:
        self._tenant_id = tenant_id

    def poll(self) -> list[RawEventPayload]:
        return [
            RawEventPayload(
                source=RawEventSource.SEC_EDGAR,
                raw_payload={
                    "title": "10-K filed by TEST Corp",
                    "companyName": "TEST Corp",
                    "category": "10-K",
                    "updated": "2026-06-01T12:00:00Z",
                },
                detected_at=datetime.now(timezone.utc),
                tenant_id=self._tenant_id,
            )
        ]

    def parse_webhook(self, body: dict) -> RawEventPayload:
        return self.poll()[0]


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Deterministic LLM mock for integration tests."""

    def __init__(self, category: str = "GEOPOLITICAL_CONFLICT", intensity: int = 3,
                 confidence: float = 0.8):
        self.category = category
        self.intensity = intensity
        self.confidence = confidence

    async def classify(self, prompt: str) -> dict:
        return {"category": self.category, "intensity": self.intensity}

    async def synthesise_confidence(self, prompt: str) -> float:
        return self.confidence
