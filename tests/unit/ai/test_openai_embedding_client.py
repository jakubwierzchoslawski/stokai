"""
Unit tests for OpenAIEmbeddingClient.

Mocks openai.AsyncOpenAI so no real API key is required.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.exceptions import PipelineError, StepTimeoutError


def _make_embedding_response(dim: int = 1536):
    response = MagicMock()
    response.data = [MagicMock(embedding=[0.01] * dim)]
    return response


@pytest.mark.asyncio
class TestOpenAIEmbeddingClient:
    """Tests for OpenAIEmbeddingClient.embed()."""

    async def test_successful_embed_returns_1536_floats(self) -> None:
        from src.ai.openai_embedding_client import OpenAIEmbeddingClient

        fake_response = _make_embedding_response(1536)

        with patch("src.ai.openai_embedding_client.openai") as mock_openai:
            mock_client_instance = MagicMock()
            mock_client_instance.embeddings.create = AsyncMock(
                return_value=fake_response
            )
            mock_openai.AsyncOpenAI.return_value = mock_client_instance

            client = OpenAIEmbeddingClient(api_key="sk-openai-test")
            result = await client.embed("Test text for embedding")

        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(v, float) for v in result)

    async def test_wrong_dimension_raises_pipeline_error(self) -> None:
        from src.ai.openai_embedding_client import OpenAIEmbeddingClient

        fake_response = _make_embedding_response(512)

        with patch("src.ai.openai_embedding_client.openai") as mock_openai:
            mock_client_instance = MagicMock()
            mock_client_instance.embeddings.create = AsyncMock(
                return_value=fake_response
            )
            mock_openai.AsyncOpenAI.return_value = mock_client_instance

            client = OpenAIEmbeddingClient(api_key="sk-openai-test")
            with pytest.raises(PipelineError, match="dimension"):
                await client.embed("Test text")

    async def test_timeout_raises_step_timeout_error(self) -> None:
        from src.ai.openai_embedding_client import OpenAIEmbeddingClient

        async def slow_embed(*args, **kwargs):
            await asyncio.sleep(999)

        with patch("src.ai.openai_embedding_client.openai") as mock_openai:
            mock_client_instance = MagicMock()
            mock_client_instance.embeddings.create = slow_embed
            mock_openai.AsyncOpenAI.return_value = mock_client_instance

            client = OpenAIEmbeddingClient(api_key="sk-openai-test")
            with pytest.raises(StepTimeoutError):
                await client.embed("text")

    async def test_api_key_not_in_exception_messages(self) -> None:
        from src.ai.openai_embedding_client import OpenAIEmbeddingClient

        with patch("src.ai.openai_embedding_client.openai") as mock_openai:
            mock_openai.OpenAIError = Exception
            mock_client_instance = MagicMock()
            mock_client_instance.embeddings.create = AsyncMock(
                side_effect=Exception("rate limit exceeded")
            )
            mock_openai.AsyncOpenAI.return_value = mock_client_instance

            client = OpenAIEmbeddingClient(api_key="sk-ultra-secret-key")
            with pytest.raises(PipelineError) as exc_info:
                await client.embed("text")

            assert "sk-ultra-secret-key" not in str(exc_info.value)
