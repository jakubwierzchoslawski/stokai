"""
ai.embedding — EmbeddingService protocol and concrete adapters.

Public surface:
    EmbeddingService — protocol that all embedding adapters satisfy.
"""
from src.ai.embedding.service import EmbeddingService

__all__ = ["EmbeddingService"]
