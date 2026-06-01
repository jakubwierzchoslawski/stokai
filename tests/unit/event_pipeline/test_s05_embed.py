"""Unit tests for EmbedStep (TASK-006, TDD).

Tests written before implementation.
Covers: AC-001.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.pipeline_state import (
    EventCategory,
    PipelineState,
    RawEventPayload,
    RawEventSource,
)


def _make_classified_state() -> PipelineState:
    tenant_id = uuid.uuid4()
    return PipelineState(
        raw_event_id=uuid.uuid4(),
        tenant_id=tenant_id,
        payload=RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload={"title": "Conflict in region"},
            detected_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        ),
        event_description="Conflict in region X",
        category=EventCategory.GEOPOLITICAL_CONFLICT,
        intensity=3,
        fingerprint="abc123",
    )


class TestEmbedStepCallsEmbeddingProvider:
    """test_embed_step_calls_embedding_provider"""

    @pytest.mark.asyncio
    async def test_embed_step_calls_embedding_provider(self):
        """EmbedStep calls embedding provider with event description text."""
        from src.event_pipeline.steps.s05_embed import EmbedStep

        fake_embedding = [0.1] * 1536
        embedding_provider_mock = AsyncMock()
        embedding_provider_mock.embed = AsyncMock(return_value=fake_embedding)

        repo_mock = AsyncMock()

        step = EmbedStep(embedding_provider=embedding_provider_mock, repo=repo_mock)
        state = _make_classified_state()

        await step.execute(state)

        embedding_provider_mock.embed.assert_called_once_with(state.event_description)


class TestEmbedStepStoresEmbeddingInState:
    """test_embed_step_stores_embedding_in_state"""

    @pytest.mark.asyncio
    async def test_embed_step_stores_embedding_in_state(self):
        """EmbedStep stores 1536-dim embedding in state.embedding."""
        from src.event_pipeline.steps.s05_embed import EmbedStep

        fake_embedding = [float(i) * 0.001 for i in range(1536)]
        embedding_provider_mock = AsyncMock()
        embedding_provider_mock.embed = AsyncMock(return_value=fake_embedding)

        repo_mock = AsyncMock()

        step = EmbedStep(embedding_provider=embedding_provider_mock, repo=repo_mock)
        state = _make_classified_state()

        result = await step.execute(state)

        assert result.embedding is not None
        assert len(result.embedding) == 1536


class TestEmbedStepWritesToGeopoliticalEvents:
    """test_embed_step_writes_to_geopolitical_events"""

    @pytest.mark.asyncio
    async def test_embed_step_writes_to_geopolitical_events(self):
        """EmbedStep calls repo.upsert_event_record with embedding data."""
        from src.event_pipeline.steps.s05_embed import EmbedStep

        fake_embedding = [0.5] * 1536
        embedding_provider_mock = AsyncMock()
        embedding_provider_mock.embed = AsyncMock(return_value=fake_embedding)

        repo_mock = AsyncMock()
        repo_mock.upsert_event_record = AsyncMock()

        step = EmbedStep(embedding_provider=embedding_provider_mock, repo=repo_mock)
        state = _make_classified_state()

        await step.execute(state)

        repo_mock.upsert_event_record.assert_called_once()
