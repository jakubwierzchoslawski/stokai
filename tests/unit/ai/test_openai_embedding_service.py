"""
Unit tests for OpenAIEmbeddingService (PLAN-F-004, TASK-001).

All OpenAI calls are mocked. No real API key required.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.embedding.exceptions import EmbeddingAPIError


def _make_embedding_response(dim: int = 1536):
    response = MagicMock()
    response.data = [MagicMock(embedding=[0.01] * dim)]
    response.usage = MagicMock(prompt_tokens=10)
    return response


@pytest.mark.asyncio
class TestOpenAIEmbeddingService:
    """Tests for OpenAIEmbeddingService.embed()."""

    async def test_embed_returns_vector_1536_length(self) -> None:
        """Mock OpenAI returns 1536 floats; assert list length 1536."""
        from src.ai.embedding.openai_embedding_service import OpenAIEmbeddingService

        fake_response = _make_embedding_response(1536)

        with patch("src.ai.embedding.openai_embedding_service.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create = AsyncMock(return_value=fake_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = OpenAIEmbeddingService(api_key="sk-test-key")
            result = await service.embed("Hello world test")

        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(v, float) for v in result)

    async def test_embed_truncates_to_500_tokens(self) -> None:
        """Input exceeding 500 tokens must be truncated before API call."""
        from src.ai.embedding.openai_embedding_service import OpenAIEmbeddingService

        fake_response = _make_embedding_response(1536)
        # Generate text significantly longer than 500 tokens (~2000+ words)
        long_text = "word " * 2000

        captured_input: list[str] = []

        async def capture_create(**kwargs):
            captured_input.append(kwargs.get("input", ""))
            return fake_response

        with patch("src.ai.embedding.openai_embedding_service.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create = capture_create
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = OpenAIEmbeddingService(api_key="sk-test-key")
            await service.embed(long_text)

        assert len(captured_input) == 1
        sent_text = captured_input[0]
        # The sent text should be shorter than the original
        assert len(sent_text) < len(long_text)

    async def test_embed_records_langfuse_span_attributes(self) -> None:
        """When span mock provided, assert tokens_in, cost_usd, model, latency_ms set."""
        from src.ai.embedding.openai_embedding_service import OpenAIEmbeddingService

        fake_response = _make_embedding_response(1536)
        fake_response.usage = MagicMock(prompt_tokens=42)

        span_mock = MagicMock()

        with patch("src.ai.embedding.openai_embedding_service.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create = AsyncMock(return_value=fake_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = OpenAIEmbeddingService(api_key="sk-test-key")
            await service.embed("Test text for span", span=span_mock)

        # span.set_attribute should have been called with tokens_in, cost_usd, model, latency_ms
        call_kwargs = {call.args[0]: call.args[1] for call in span_mock.set_attribute.call_args_list}
        assert "tokens_in" in call_kwargs
        assert "cost_usd" in call_kwargs
        assert "model" in call_kwargs
        assert "latency_ms" in call_kwargs
        assert call_kwargs["tokens_in"] == 42
        assert call_kwargs["model"] == "text-embedding-3-small"
        # cost_usd = tokens_in * 0.00000002
        assert abs(call_kwargs["cost_usd"] - 42 * 0.00000002) < 1e-10

    async def test_embed_raises_embedding_api_error_on_http_failure(self) -> None:
        """Mock raises openai.APIError; assert EmbeddingAPIError raised."""
        from src.ai.embedding.openai_embedding_service import OpenAIEmbeddingService

        with patch("src.ai.embedding.openai_embedding_service.openai") as mock_openai:
            api_error = Exception("HTTP 500")
            mock_openai.APIError = type("APIError", (Exception,), {})
            mock_client = MagicMock()
            mock_client.embeddings.create = AsyncMock(
                side_effect=mock_openai.APIError("HTTP 500")
            )
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = OpenAIEmbeddingService(api_key="sk-test-key")
            with pytest.raises(EmbeddingAPIError):
                await service.embed("some text")
