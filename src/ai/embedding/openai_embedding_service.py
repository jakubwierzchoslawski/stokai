"""
OpenAIEmbeddingService — EmbeddingService implementation backed by OpenAI's API.

Uses text-embedding-3-small (1536 dimensions, cl100k_base tokenizer).
Truncates input to 500 tokens before the API call (Principle 2: cost control).
Records a Langfuse child span when `span` is provided.

Security: the API key is NEVER logged or included in exception messages.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import openai
import tiktoken

from src.ai.embedding.exceptions import EmbeddingAPIError, EmbeddingTimeoutError

_MODEL = "text-embedding-3-small"
_MAX_TOKENS = 500
_COST_PER_TOKEN = 0.00000002  # $0.02 / 1M tokens
_TOKENIZER = "cl100k_base"


class OpenAIEmbeddingService:
    """Async embedding service backed by OpenAI text-embedding-3-small.

    Args:
        api_key: OpenAI API key — never logged or included in exceptions.
    """

    def __init__(self, api_key: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._encoder = tiktoken.get_encoding(_TOKENIZER)

    def _truncate(self, text: str) -> str:
        """Truncate *text* to at most _MAX_TOKENS tokens."""
        tokens = self._encoder.encode(text)
        if len(tokens) <= _MAX_TOKENS:
            return text
        return self._encoder.decode(tokens[:_MAX_TOKENS])

    async def embed(self, text: str, span: Any | None = None) -> list[float]:
        """Embed *text* using text-embedding-3-small.

        Truncates input to 500 tokens before calling the API.
        When *span* is provided, records tokens_in, cost_usd, model, latency_ms
        via ``span.set_attribute()``.

        Returns:
            Dense float vector of 1536 dimensions.

        Raises:
            EmbeddingAPIError: On API error or unexpected response.
            EmbeddingTimeoutError: On asyncio timeout (caller-provided wait_for).
        """
        truncated = self._truncate(text)
        tokens_encoded = self._encoder.encode(truncated)
        tokens_in = len(tokens_encoded)

        t0 = time.monotonic()
        try:
            response = await self._client.embeddings.create(
                model=_MODEL,
                input=truncated,
            )
        except openai.APIError as exc:
            raise EmbeddingAPIError(
                f"OpenAI Embeddings API error: {type(exc).__name__}"
            ) from None
        except asyncio.TimeoutError as exc:
            raise EmbeddingTimeoutError(
                "Embedding request timed out"
            ) from exc
        except Exception as exc:
            raise EmbeddingAPIError(
                f"Unexpected error during embedding: {type(exc).__name__}"
            ) from None

        latency_ms = int((time.monotonic() - t0) * 1000)
        cost_usd = tokens_in * _COST_PER_TOKEN

        vector: list[float] = response.data[0].embedding

        if span is not None:
            span.set_attribute("tokens_in", tokens_in)
            span.set_attribute("cost_usd", cost_usd)
            span.set_attribute("model", _MODEL)
            span.set_attribute("latency_ms", latency_ms)

        return vector
