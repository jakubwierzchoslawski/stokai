"""
OpenAIEmbeddingClient — IEmbeddingClient implementation backed by the OpenAI API.

Uses text-embedding-3-small (1536 dimensions).
Security note: the API key is never logged or included in exception messages.
"""
from __future__ import annotations

import asyncio
import logging

import openai

from src.events.exceptions import PipelineError, StepTimeoutError

logger = logging.getLogger(__name__)

_EXPECTED_DIM = 1536
_TIMEOUT_SECONDS = 2.0
_MODEL = "text-embedding-3-small"


class OpenAIEmbeddingClient:
    """Async embedding client backed by OpenAI's Embeddings API.

    Args:
        api_key: OpenAI API key — never logged or included in exceptions.
    """

    def __init__(self, api_key: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)

    # ── IEmbeddingClient ──────────────────────────────────────────────────────

    async def embed(self, text: str) -> list[float]:
        """Embed *text* using text-embedding-3-small.

        Enforces a hard 2-second timeout.

        Returns:
            Dense float vector of exactly 1536 dimensions.

        Raises:
            StepTimeoutError: When the request exceeds 2 seconds.
            PipelineError: On API errors or dimension mismatch.
        """
        try:
            response = await asyncio.wait_for(
                self._client.embeddings.create(
                    model=_MODEL,
                    input=text,
                ),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise StepTimeoutError(
                f"Embedding request timed out after {_TIMEOUT_SECONDS}s"
            ) from exc
        except openai.OpenAIError as exc:
            raise PipelineError(
                f"OpenAI API error: {type(exc).__name__}"
            ) from None
        except Exception as exc:
            raise PipelineError(
                f"Unexpected error during embedding: {type(exc).__name__}"
            ) from None

        vector: list[float] = response.data[0].embedding
        if len(vector) != _EXPECTED_DIM:
            raise PipelineError(
                f"Embedding dimension mismatch: expected {_EXPECTED_DIM}, got {len(vector)}"
            )
        return vector
