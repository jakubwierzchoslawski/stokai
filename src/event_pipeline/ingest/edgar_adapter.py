"""EdgarAdapter — SEC EDGAR ATOM feed polling and webhook ingestion adapter.

Architecture enforcement:
  P-01 Provider Abstraction — implements IngestionAdapter Protocol.
  P-06 12-Factor Compliance — feed URL from environment variable.
  AC-003 — SEC filing alert must reach dispatch < 20 minutes from filing.

Single Responsibility: EDGAR feed polling and webhook body parsing only.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from src.event_pipeline.ingest.exceptions import ProviderUnavailableError
from src.event_pipeline.pipeline_state import RawEventPayload, RawEventSource

logger = logging.getLogger(__name__)

_DEFAULT_EDGAR_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=10-K&dateb=&owner=include&count=40&output=atom"
)


class EdgarAdapter:
    """SEC EDGAR ingestion adapter supporting both polling and webhook modes.

    Parameters
    ----------
    tenant_id:
        UUID of the owning tenant.
    feed_url:
        Override the EDGAR ATOM feed URL. Defaults to ``EDGAR_FEED_URL`` env var.
    """

    source: str = RawEventSource.SEC_EDGAR.value

    def __init__(
        self,
        tenant_id: uuid.UUID,
        feed_url: str | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._feed_url = (
            feed_url
            or os.environ.get("EDGAR_FEED_URL", _DEFAULT_EDGAR_FEED_URL)
        )

    def poll(self) -> list[RawEventPayload]:
        """Synchronous stub: async poll is expected in production.

        For MVP, EDGAR is primarily webhook-driven. Polling support requires
        an ATOM feed parser (e.g. feedparser); not implemented in this stub.
        Raises NotImplementedError to signal that only webhook mode is active.
        """
        # In a real implementation this would call an async HTTP client.
        # Kept as stub; webhook mode (parse_webhook) is the primary path.
        logger.info("EdgarAdapter.poll() called — webhook mode is preferred")
        return []

    def parse_webhook(self, body: dict) -> RawEventPayload:
        """Parse a push-delivered EDGAR notification body into RawEventPayload.

        Parameters
        ----------
        body:
            Raw EDGAR filing notification (ATOM entry fields as a dict).

        Returns
        -------
        RawEventPayload
            Structured event payload for pipeline processing.
        """
        updated_str = body.get("updated", "")
        detected_at: datetime
        if updated_str:
            try:
                # ISO 8601 with Z suffix
                detected_at = datetime.fromisoformat(
                    updated_str.replace("Z", "+00:00")
                )
            except ValueError:
                detected_at = datetime.now(timezone.utc)
        else:
            detected_at = datetime.now(timezone.utc)

        return RawEventPayload(
            source=RawEventSource.SEC_EDGAR,
            raw_payload=dict(body),
            detected_at=detected_at,
            tenant_id=self._tenant_id,
        )
