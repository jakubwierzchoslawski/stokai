"""
EmbeddingService protocol — the only abstraction callers depend on.

All concrete adapters (e.g. OpenAIEmbeddingService) must satisfy this protocol.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EmbeddingService(Protocol):
    """Protocol for embedding services that convert text to dense float vectors."""

    async def embed(self, text: str, span: Any | None = None) -> list[float]:
        """Embed *text* and return a dense float vector.

        Args:
            text: Input text to embed. Implementations may truncate as needed.
            span: Optional observability span for recording call metadata.
                  When provided, implementations SHOULD record tokens_in,
                  cost_usd, model, and latency_ms via span.set_attribute().

        Returns:
            Dense float vector (length determined by underlying model).

        Raises:
            EmbeddingAPIError: On API failure or unexpected response.
            EmbeddingTimeoutError: When the request exceeds the timeout budget.
        """
        ...
