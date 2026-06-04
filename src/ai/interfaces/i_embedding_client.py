"""
IEmbeddingClient — protocol for OpenAI (and future) embedding clients.
"""
from __future__ import annotations

from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class IEmbeddingClient(Protocol):
    """Interface for converting text into dense float vectors.

    The expected vector dimension is 1536 (text-embedding-3-small).
    """

    async def embed(self, text: str) -> list[float]:
        """Embed *text* into a dense float vector.

        Args:
            text: Input text to embed.

        Returns:
            Dense float vector of exactly 1536 dimensions.

        Raises:
            StepTimeoutError: When the request exceeds the client's timeout.
            PipelineError: On provider API errors or dimension mismatch.
        """
        ...
