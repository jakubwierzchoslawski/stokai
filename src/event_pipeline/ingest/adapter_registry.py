"""AdapterRegistry — maps RawEventSource to IngestionAdapter instances.

Architecture enforcement:
  P-01 Provider Abstraction — registry dispatches to typed adapters only.
  C-002 — Twitter/X toggle defaults OFF; controlled via TWITTER_ENABLED env var.
  P-06 12-Factor Compliance — toggle state read from environment variable.

Single Responsibility: maps source enum to adapter instance and checks enable state.
Dependency Inversion: adapters are constructed with injected tenant_id; registry
  does not instantiate concrete adapters beyond its own factory.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from src.event_pipeline.pipeline_state import RawEventSource

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Registry that maps RawEventSource values to IngestionAdapter instances.

    Parameters
    ----------
    tenant_id:
        UUID of the owning tenant passed to each adapter.
    redis_client:
        Optional Redis client forwarded to PriceAnomalyAdapter.
    """

    def __init__(
        self,
        tenant_id: uuid.UUID,
        redis_client: Any = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._redis_client = redis_client
        self._twitter_enabled: bool = self._read_twitter_toggle()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_enabled(self, source: RawEventSource) -> bool:
        """Return True if the given source adapter is enabled.

        Twitter/X is controlled by the ``TWITTER_ENABLED`` env var (C-002).
        All other sources default to enabled.
        """
        if source == RawEventSource.X_FILTERED_STREAM:
            return self._twitter_enabled
        return True

    def get_adapter(self, source: RawEventSource) -> Any:
        """Return the IngestionAdapter for *source*, or None if disabled.

        If the source is disabled, logs at INFO level and returns None.
        """
        if not self.is_enabled(source):
            logger.info(
                "AdapterRegistry: source %r is disabled — skipping",
                source.value,
            )
            return None

        return self._build_adapter(source)

    def get_all_enabled_adapters(self) -> list[Any]:
        """Return a list of all enabled IngestionAdapter instances."""
        adapters = []
        for source in RawEventSource:
            adapter = self.get_adapter(source)
            if adapter is not None:
                adapters.append(adapter)
        return adapters

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_twitter_toggle() -> bool:
        """Read TWITTER_ENABLED env var; default is False (C-002)."""
        raw = os.environ.get("TWITTER_ENABLED", "false").strip().lower()
        return raw in ("1", "true", "yes")

    def _build_adapter(self, source: RawEventSource) -> Any:
        """Construct the adapter for *source* with injected tenant_id."""
        from src.event_pipeline.ingest.gdelt_adapter import GdeltAdapter
        from src.event_pipeline.ingest.edgar_adapter import EdgarAdapter
        from src.event_pipeline.ingest.price_anomaly_adapter import PriceAnomalyAdapter
        from src.event_pipeline.ingest.twitter_stub_adapter import TwitterStubAdapter

        constructors = {
            RawEventSource.GDELT: lambda: GdeltAdapter(tenant_id=self._tenant_id),
            RawEventSource.SEC_EDGAR: lambda: EdgarAdapter(tenant_id=self._tenant_id),
            RawEventSource.PRICE_ANOMALY: lambda: PriceAnomalyAdapter(
                tenant_id=self._tenant_id,
                redis_client=self._redis_client,
            ),
            RawEventSource.X_FILTERED_STREAM: lambda: TwitterStubAdapter(
                tenant_id=self._tenant_id
            ),
        }

        constructor = constructors.get(source)
        if constructor is None:
            raise ValueError(f"No adapter registered for source: {source!r}")
        return constructor()
