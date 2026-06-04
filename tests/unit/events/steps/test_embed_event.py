"""
Unit tests for the embed_event step.

Updated for PLAN-F-004: step now uses EmbeddingService protocol
and EventEmbeddingRepository protocol (with idempotency).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.exceptions import StepTimeoutError
from src.events.models import ClassificationResult, PipelineContext, RawEvent
from src.events.steps.embed_event import embed_event


def _make_ctx(title: str = "Test Title", summary: str = "Test Summary") -> PipelineContext:
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": title, "summary": summary},
        ),
        event_id=uuid.uuid4(),
        langfuse_span=None,
    )


@pytest.mark.asyncio
class TestEmbedEvent:

    async def test_embedding_stored_in_ctx_and_repository(self) -> None:
        ctx = _make_ctx()
        embedding_service = AsyncMock()
        embedding_service.embed = AsyncMock(return_value=[0.01] * 1536)
        embedding_repo = AsyncMock()
        embedding_repo.get_by_event_id = AsyncMock(return_value=None)
        embedding_repo.save = AsyncMock(return_value=None)

        result = await embed_event(ctx, embedding_service, embedding_repo)

        assert result.embedding is not None
        assert len(result.embedding) == 1536
        embedding_repo.save.assert_called_once_with(ctx.event_id, [0.01] * 1536)

    async def test_timeout_propagates_as_step_timeout_error(self) -> None:
        import asyncio
        ctx = _make_ctx()
        embedding_service = AsyncMock()

        async def slow_embed(text, span=None):
            await asyncio.sleep(3)
            return [0.0] * 1536

        embedding_service.embed = slow_embed
        embedding_repo = AsyncMock()
        embedding_repo.get_by_event_id = AsyncMock(return_value=None)

        with pytest.raises(StepTimeoutError):
            await embed_event(ctx, embedding_service, embedding_repo, timeout_seconds=0.05)

    async def test_text_passed_is_title_plus_summary(self) -> None:
        ctx = _make_ctx(title="MyTitle", summary="MySummary")
        embedding_service = AsyncMock()
        embedding_service.embed = AsyncMock(return_value=[0.0] * 1536)
        embedding_repo = AsyncMock()
        embedding_repo.get_by_event_id = AsyncMock(return_value=None)
        embedding_repo.save = AsyncMock(return_value=None)

        await embed_event(ctx, embedding_service, embedding_repo)

        call_args = embedding_service.embed.call_args
        text_arg = call_args[0][0] if call_args[0] else call_args.kwargs.get("text", "")
        assert "MyTitle" in text_arg
        assert "MySummary" in text_arg

    async def test_skips_api_when_embedding_already_cached(self) -> None:
        """embed_event returns cached embedding without calling service."""
        ctx = _make_ctx()
        cached_vector = [0.99] * 1536
        embedding_service = AsyncMock()
        embedding_service.embed = AsyncMock(return_value=[0.01] * 1536)
        embedding_repo = AsyncMock()
        embedding_repo.get_by_event_id = AsyncMock(return_value=cached_vector)
        embedding_repo.save = AsyncMock(return_value=None)

        result = await embed_event(ctx, embedding_service, embedding_repo)

        embedding_service.embed.assert_not_called()
        embedding_repo.save.assert_not_called()
        assert result.embedding == cached_vector
