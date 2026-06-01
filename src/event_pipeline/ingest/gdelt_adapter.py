"""GdeltAdapter — GDELT v2 HTTP polling ingestion adapter.

Architecture enforcement:
  P-01 Provider Abstraction — implements IngestionAdapter Protocol.
  P-06 12-Factor Compliance — API URL from environment variable.
  AC-003 — geo-events should reach alert dispatch < 90 s.

Single Responsibility: HTTP polling of GDELT and conversion to RawEventPayload.
Dependency Inversion: httpx client injected or created internally; no global state.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from src.event_pipeline.ingest.exceptions import ProviderUnavailableError
from src.event_pipeline.pipeline_state import RawEventPayload, RawEventSource

logger = logging.getLogger(__name__)

# Default GDELT v2 GKG (Global Knowledge Graph) news/event API endpoint
_DEFAULT_GDELT_API_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query=conflict&mode=artlist&maxrecords=250&format=json"
)


class GdeltAdapter:
    """HTTP polling adapter for the GDELT v2 event API.

    Parameters
    ----------
    tenant_id:
        UUID of the owning tenant; stored in every produced RawEventPayload.
    api_url:
        Override the GDELT API URL. Defaults to ``GDELT_API_URL`` env var or the
        built-in default query.
    """

    source: str = RawEventSource.GDELT.value

    def __init__(
        self,
        tenant_id: uuid.UUID,
        api_url: str | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._api_url = (
            api_url
            or os.environ.get("GDELT_API_URL", _DEFAULT_GDELT_API_URL)
        )

    async def poll(self) -> list[RawEventPayload]:
        """Fetch events from the GDELT v2 API and convert to RawEventPayload list.

        Returns
        -------
        list[RawEventPayload]
            Parsed GDELT events as pipeline-ready payloads.

        Raises
        ------
        ProviderUnavailableError
            On any HTTP error (4xx, 5xx, connection failure).
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self._api_url)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"GDELT API returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(
                f"GDELT API request failed: {exc}"
            ) from exc

        return self._parse_response(data)

    def parse_webhook(self, body: dict) -> RawEventPayload:
        """Parse a single GDELT event pushed via webhook.

        Parameters
        ----------
        body:
            Raw GDELT article or event entry as a dict.
        """
        return self._article_to_payload(body)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_response(self, data: dict[str, Any]) -> list[RawEventPayload]:
        """Convert GDELT API response JSON into RawEventPayload list."""
        articles = data.get("articles", [])
        payloads = []
        for article in articles:
            try:
                payloads.append(self._article_to_payload(article))
            except Exception:  # noqa: BLE001
                logger.warning("Skipping malformed GDELT article: %r", article)
        return payloads

    def _article_to_payload(self, article: dict[str, Any]) -> RawEventPayload:
        """Convert a single GDELT article dict to RawEventPayload."""
        # Parse seendate: "20260601T120000Z" -> datetime
        seen_str = article.get("seendate", "")
        detected_at: datetime
        if seen_str:
            try:
                detected_at = datetime.strptime(seen_str, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                detected_at = datetime.now(timezone.utc)
        else:
            detected_at = datetime.now(timezone.utc)

        return RawEventPayload(
            source=RawEventSource.GDELT,
            raw_payload=dict(article),
            detected_at=detected_at,
            tenant_id=self._tenant_id,
        )
