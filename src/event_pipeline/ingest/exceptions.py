"""Ingest-layer exceptions.

Single Responsibility: exception definitions only.
"""
from __future__ import annotations


class ProviderUnavailableError(Exception):
    """Raised when an external data provider returns a non-success HTTP status."""


class ProviderDisabled(Exception):
    """Raised when an adapter is disabled via admin toggle."""
