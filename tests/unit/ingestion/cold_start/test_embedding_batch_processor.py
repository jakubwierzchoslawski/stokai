"""
Unit tests for EmbeddingBatchProcessor.

All external dependencies (EmbeddingService, EventEmbeddingRepository) are mocked.
Tests cover happy path, idempotency, retry logic, and concurrency batching.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.ingestion.cold_start.embedding_batch_processor import (
    EmbeddingBatchError,
    EmbeddingBatchProcessor,
)

_FAKE_EMBEDDING = [0.1] * 1536

_EV1 = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_EV2 = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
_EV3 = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003")


def _make_embedding_service(embedding=None, side_effect=None) -> AsyncMock:
    svc = AsyncMock()
    if side_effect is not None:
        svc.embed = AsyncMock(side_effect=side_effect)
    else:
        svc.embed = AsyncMock(return_value=embedding or _FAKE_EMBEDDING)
    return svc


def _make_embedding_repo(existing_ids=None) -> AsyncMock:
    """Mock repository that reports existing event_ids as already embedded."""
    repo = AsyncMock()
    existing = set(existing_ids or [])

    async def has_embedding(event_id):
        return event_id in existing

    repo.event_has_embedding = AsyncMock(side_effect=has_embedding)
    repo.upsert_embedding = AsyncMock()
    return repo


class _RateLimitError(Exception):
    """Simulates openai.RateLimitError for testing."""
    pass


class _APIError(Exception):
    """Simulates openai.APIError for testing."""
    pass


@pytest.mark.unit
class TestHappyPath:
    """Tests for the normal embedding path."""

    @pytest.mark.asyncio
    async def test_process_batch_calls_embed_once_per_event(self):
        """Happy path: process_batch calls EmbeddingService.embed once per event."""
        svc = _make_embedding_service()
        repo = _make_embedding_repo()
        processor = EmbeddingBatchProcessor(svc, repo, concurrency=5)

        items = [(_EV1, "text one"), (_EV2, "text two")]
        created = await processor.process_batch(items)

        assert created == 2
        assert svc.embed.call_count == 2
        svc.embed.assert_any_call("text one")
        svc.embed.assert_any_call("text two")
        assert repo.upsert_embedding.call_count == 2

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write_to_repo(self):
        """dry_run=True generates embeddings but does not call upsert_embedding."""
        svc = _make_embedding_service()
        repo = _make_embedding_repo()
        processor = EmbeddingBatchProcessor(svc, repo, concurrency=5)

        items = [(_EV1, "text one")]
        created = await processor.process_batch(items, dry_run=True)

        assert created == 1
        svc.embed.assert_called_once()
        repo.upsert_embedding.assert_not_called()


@pytest.mark.unit
class TestIdempotency:
    """Tests for skipping already-embedded events."""

    @pytest.mark.asyncio
    async def test_already_embedded_event_skipped(self):
        """Already-embedded event_id: repository check returns True; embed is NOT called."""
        svc = _make_embedding_service()
        repo = _make_embedding_repo(existing_ids=[_EV1])
        processor = EmbeddingBatchProcessor(svc, repo, concurrency=5)

        items = [(_EV1, "text for ev1"), (_EV2, "text for ev2")]
        created = await processor.process_batch(items)

        # Only _EV2 should be embedded
        assert created == 1
        svc.embed.assert_called_once_with("text for ev2")
        repo.upsert_embedding.assert_called_once()


@pytest.mark.unit
class TestRetryLogic:
    """Tests for exponential backoff retry on rate limit errors."""

    @pytest.mark.asyncio
    async def test_rate_limit_error_retried_succeeds_on_second_attempt(self):
        """RateLimitError on first attempt: retried; succeeds on second attempt."""
        call_count = [0]

        async def embed_side_effect(text):
            call_count[0] += 1
            if call_count[0] == 1:
                raise _RateLimitError("rate limited")
            return _FAKE_EMBEDDING

        svc = _make_embedding_service(side_effect=embed_side_effect)
        repo = _make_embedding_repo()
        processor = EmbeddingBatchProcessor(svc, repo, concurrency=5)

        # Patch asyncio.sleep to avoid actual waiting
        with patch("src.ingestion.cold_start.embedding_batch_processor.asyncio.sleep", new=AsyncMock()):
            created = await processor.process_batch([(_EV1, "text")])

        assert created == 1
        assert call_count[0] == 2  # One failure + one success

    @pytest.mark.asyncio
    async def test_three_consecutive_rate_limit_errors_raises_batch_error(self):
        """Three consecutive RateLimitErrors → EmbeddingBatchError after max retries."""
        async def always_rate_limit(text):
            raise _RateLimitError("always rate limited")

        svc = _make_embedding_service(side_effect=always_rate_limit)
        repo = _make_embedding_repo()
        processor = EmbeddingBatchProcessor(svc, repo, concurrency=5)

        with patch("src.ingestion.cold_start.embedding_batch_processor.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(EmbeddingBatchError):
                await processor.process_batch([(_EV1, "text")])


@pytest.mark.unit
class TestConcurrency:
    """Tests for parallel batching behavior."""

    @pytest.mark.asyncio
    async def test_concurrency_3_with_6_events_called_in_two_batches(self):
        """With concurrency=3 and 6 events, embed called in two parallel batches."""
        batch_sizes: list[int] = []
        gather_calls: list[int] = []

        original_gather = asyncio.gather

        # Track how many coroutines are gathered at once
        async def mock_gather(*coros, **kwargs):
            gather_calls.append(len(coros))
            return await original_gather(*coros, **kwargs)

        svc = _make_embedding_service()
        repo = _make_embedding_repo()
        processor = EmbeddingBatchProcessor(svc, repo, concurrency=3)

        events = [(uuid.uuid4(), f"text {i}") for i in range(6)]

        with patch(
            "src.ingestion.cold_start.embedding_batch_processor.asyncio.gather",
            side_effect=mock_gather,
        ):
            created = await processor.process_batch(events)

        assert created == 6
        # Two batches of 3 each
        assert len(gather_calls) == 2
        assert all(n == 3 for n in gather_calls)
