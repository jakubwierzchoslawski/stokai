"""
Unit tests for embed_event step (PLAN-F-004, TASK-003).

Tests the new EmbeddingService + EventEmbeddingRepository protocol-based
implementation with idempotency and timeout enforcement.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.exceptions import PipelineError, StepTimeoutError
from src.events.models import PipelineContext, RawEvent
from src.events.steps.embed_event import embed_event


def _make_ctx(event_id=None) -> PipelineContext:
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": "Test Title", "summary": "Test Summary"},
        ),
        event_id=event_id or uuid.uuid4(),
        langfuse_span=None,
    )


def _make_embedding_service(vector=None) -> AsyncMock:
    svc = AsyncMock()
    svc.embed = AsyncMock(return_value=vector or [0.01] * 1536)
    return svc


def _make_embedding_repo(existing=None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_event_id = AsyncMock(return_value=existing)
    repo.save = AsyncMock(return_value=None)
    return repo


@pytest.mark.asyncio
class TestEmbedEvent:
    """Tests for embed_event step function."""

    async def test_embed_event_calls_api_and_persists_when_not_cached(self) -> None:
        """mock repo returns None; assert service.embed called once; assert repo.save called."""
        ctx = _make_ctx()
        svc = _make_embedding_service()
        repo = _make_embedding_repo(existing=None)

        result = await embed_event(ctx, svc, repo)

        svc.embed.assert_called_once()
        repo.save.assert_called_once_with(ctx.event_id, [0.01] * 1536)
        assert result.embedding == [0.01] * 1536

    async def test_embed_event_skips_api_when_already_persisted(self) -> None:
        """mock repo returns existing embedding; assert service.embed NOT called."""
        cached_vector = [0.99] * 1536
        ctx = _make_ctx()
        svc = _make_embedding_service()
        repo = _make_embedding_repo(existing=cached_vector)

        result = await embed_event(ctx, svc, repo)

        svc.embed.assert_not_called()
        repo.save.assert_not_called()
        assert result.embedding == cached_vector

    async def test_embed_event_populates_ctx_embedding(self) -> None:
        """ctx.embedding populated after successful embed."""
        vector = [0.5] * 1536
        ctx = _make_ctx()
        svc = _make_embedding_service(vector=vector)
        repo = _make_embedding_repo(existing=None)

        result = await embed_event(ctx, svc, repo)

        assert result.embedding is not None
        assert len(result.embedding) == 1536
        assert result.embedding == vector

    async def test_embed_event_raises_step_timeout_error(self) -> None:
        """mock service.embed sleeps 3s; assert StepTimeoutError on 0.05s timeout."""
        ctx = _make_ctx()

        async def slow_embed(text, span=None):
            await asyncio.sleep(3)
            return [0.0] * 1536

        svc = AsyncMock()
        svc.embed = slow_embed
        repo = _make_embedding_repo(existing=None)

        with pytest.raises(StepTimeoutError):
            await embed_event(ctx, svc, repo, timeout_seconds=0.05)

    async def test_embed_event_raises_pipeline_error_when_no_event_id(self) -> None:
        """Raise PipelineError when ctx.event_id is None."""
        ctx = _make_ctx()
        ctx.event_id = None
        svc = _make_embedding_service()
        repo = _make_embedding_repo()

        with pytest.raises(PipelineError):
            await embed_event(ctx, svc, repo)

    async def test_embed_event_passes_langfuse_span_to_service(self) -> None:
        """ctx.langfuse_span is forwarded to embedding_service.embed."""
        span_mock = MagicMock()
        ctx = _make_ctx()
        ctx.langfuse_span = span_mock
        svc = _make_embedding_service()
        repo = _make_embedding_repo(existing=None)

        await embed_event(ctx, svc, repo)

        svc.embed.assert_called_once()
        call_kwargs = svc.embed.call_args
        # span should be passed as keyword arg
        assert call_kwargs.kwargs.get("span") is span_mock or call_kwargs.args[1] is span_mock
