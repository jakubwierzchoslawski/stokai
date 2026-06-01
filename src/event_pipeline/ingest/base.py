"""IngestionAdapter Protocol — the interface every source adapter must satisfy.

Single Responsibility: defines only the ingestion contract.
Interface Segregation: minimal interface; adapters that need additional
  collaborators receive them via their ``__init__``, not here.

Architecture enforcement:
  P-01 Provider Abstraction — all ingestion adapters implement this Protocol;
    no direct API calls are made outside adapter implementations.
"""
from __future__ import annotations

from typing import Protocol

from src.event_pipeline.pipeline_state import RawEventPayload


class IngestionAdapter(Protocol):
    """Structural protocol for all ingestion source adapters.

    Adapters implement ``poll()`` for scheduled/periodic ingestion, and
    optionally ``parse_webhook()`` for push-based sources (e.g. SEC EDGAR).
    """

    source: str  # matches RawEventSource enum value

    def poll(self) -> list[RawEventPayload]:
        """Poll the data source and return newly ingested events.

        Returns
        -------
        list[RawEventPayload]
            Zero or more raw event payloads ready for pipeline processing.

        Raises
        ------
        ProviderUnavailableError
            If the external source is unreachable.
        ProviderDisabled
            If the source is disabled via admin toggle.
        """
        ...

    def parse_webhook(self, body: dict) -> RawEventPayload:
        """Parse a push-delivered webhook body into a RawEventPayload.

        Parameters
        ----------
        body:
            Raw webhook payload dictionary.

        Returns
        -------
        RawEventPayload
            Structured event payload.
        """
        ...
