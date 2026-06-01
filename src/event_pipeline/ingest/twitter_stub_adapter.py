"""TwitterStubAdapter — SocialProvider stub; admin toggle defaults OFF (C-002).

Architecture enforcement:
  P-01 Provider Abstraction — implements IngestionAdapter Protocol.
  C-002 — Free API only; stub raises ProviderDisabled when called.

Single Responsibility: raises ProviderDisabled on any poll() call to signal
  that Twitter/X is not connected in MVP.

No live API connection is made in this module.
"""
from __future__ import annotations

import uuid

from src.event_pipeline.ingest.exceptions import ProviderDisabled
from src.event_pipeline.pipeline_state import RawEventPayload, RawEventSource


class TwitterStubAdapter:
    """Stub adapter for Twitter/X Free API.

    Admin toggle defaults OFF (C-002).  This adapter exists so the toggle can
    activate a real implementation later without any other code changes.

    ``poll()`` always raises ``ProviderDisabled``.
    """

    source: str = RawEventSource.X_FILTERED_STREAM.value

    def __init__(self, tenant_id: uuid.UUID) -> None:
        self._tenant_id = tenant_id

    def poll(self) -> list[RawEventPayload]:
        """Always raises ProviderDisabled — Twitter/X is not connected in MVP."""
        raise ProviderDisabled(
            "Twitter/X toggle is OFF (C-002). "
            "No live API connection in MVP. "
            "Enable via TWITTER_ENABLED=true when a live adapter is implemented."
        )

    def parse_webhook(self, body: dict) -> RawEventPayload:
        """Not implemented — Twitter/X Free API does not support webhooks in MVP."""
        raise ProviderDisabled(
            "TwitterStubAdapter does not support webhook parsing. "
            "Toggle is OFF (C-002)."
        )
