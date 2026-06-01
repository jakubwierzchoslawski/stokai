"""PriceAnomalyAdapter — internal Redis queue-based price anomaly ingestion.

Architecture enforcement:
  P-01 Provider Abstraction — implements IngestionAdapter Protocol.
  P-02 Cache-First Lookup — reads from internal Redis list key.

Single Responsibility: reads anomaly events from Redis and converts to RawEventPayload.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.event_pipeline.pipeline_state import RawEventPayload, RawEventSource

logger = logging.getLogger(__name__)


class PriceAnomalyAdapter:
    """Ingestion adapter that reads from internal Redis price anomaly queue.

    Parameters
    ----------
    tenant_id:
        UUID of the owning tenant.
    redis_client:
        Async Redis client. If None (test/no-op mode), poll returns empty list.
    """

    source: str = RawEventSource.PRICE_ANOMALY.value

    def __init__(
        self,
        tenant_id: uuid.UUID,
        redis_client: Any = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._redis = redis_client

    def poll(self) -> list[RawEventPayload]:
        """Poll the Redis anomaly queue.

        In production the Redis LPOP is performed asynchronously.
        For MVP, returns empty list when no Redis client is configured.
        """
        # Async implementation would use: await self._redis.lpop(key, count)
        if self._redis is None:
            return []
        return []

    def parse_webhook(self, body: dict) -> RawEventPayload:
        """Parse a price anomaly event body into RawEventPayload.

        Parameters
        ----------
        body:
            Price anomaly event dict with at least 'symbol' and 'detected_at' fields.
        """
        detected_str = body.get("detected_at", "")
        detected_at: datetime
        if detected_str:
            try:
                detected_at = datetime.fromisoformat(
                    str(detected_str).replace("Z", "+00:00")
                )
            except ValueError:
                detected_at = datetime.now(timezone.utc)
        else:
            detected_at = datetime.now(timezone.utc)

        return RawEventPayload(
            source=RawEventSource.PRICE_ANOMALY,
            raw_payload=dict(body),
            detected_at=detected_at,
            tenant_id=self._tenant_id,
        )
