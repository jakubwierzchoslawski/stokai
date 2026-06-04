"""
Exceptions for the ai.embedding module (PLAN-F-004).
"""


class EmbeddingAPIError(Exception):
    """Raised when the OpenAI Embeddings API returns an error or unexpected response."""


class EmbeddingTimeoutError(EmbeddingAPIError):
    """Raised when an embedding request exceeds the configured timeout."""
