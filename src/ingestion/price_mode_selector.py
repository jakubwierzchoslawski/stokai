"""PriceModeSelector — config-driven price freshness TTL resolver.

Reads the ``price_freshness_mode`` key from the ``source_config`` table on
every call so that an admin panel toggle takes effect immediately on the next
ingestion cycle — no code change, no service restart required (AC-005).

Freshness modes:
    "delayed"  — 15-minute-delayed data; TTL = 900 seconds (default)
    "realtime" — real-time data; TTL = 5 seconds

The ``CacheOrFetch`` decorator for price bar data should call
``PriceModeSelector.get_price_ttl()`` instead of using the static TTL from
``DEFAULT_TTL_REGISTRY``, so that the mode change propagates automatically.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_DELAYED_TTL_SECONDS = 900   # 15 minutes — default for free-tier data
_REALTIME_TTL_SECONDS = 5    # 5 seconds — real-time feed


class PriceFreshnessMode:
    """Constants for price freshness mode values."""

    DELAYED = "delayed"
    REALTIME = "realtime"


class PriceModeSelector:
    """Reads price freshness mode from ``source_config`` and returns the TTL.

    No cached value — always reads current config on each call so that an
    admin panel toggle takes effect on the next request.

    Args:
        get_source_config: Async callable that accepts a ``source_id`` string
            and returns a ``dict`` of configuration values for that source.
            In production this queries the ``source_config`` table.
    """

    def __init__(
        self,
        get_source_config: Callable[[str], Awaitable[dict]],
    ) -> None:
        self._get_source_config = get_source_config

    async def get_price_ttl(self, source_id: str = "price_provider") -> int:
        """Return the TTL in seconds appropriate for the current price freshness mode.

        Args:
            source_id: The source_config row to read; defaults to
                ``"price_provider"``.

        Returns:
            900 if the mode is ``"delayed"`` (or unrecognised/missing).
            5   if the mode is ``"realtime"``.
        """
        try:
            config = await self._get_source_config(source_id)
        except Exception as exc:
            logger.warning(
                "Failed to read source_config for %r: %s — defaulting to delayed mode",
                source_id,
                exc,
            )
            return _DELAYED_TTL_SECONDS

        mode = config.get("price_freshness_mode", PriceFreshnessMode.DELAYED)

        if mode == PriceFreshnessMode.REALTIME:
            return _REALTIME_TTL_SECONDS

        if mode != PriceFreshnessMode.DELAYED:
            logger.warning(
                "Unrecognised price_freshness_mode %r for source %r; defaulting to delayed",
                mode,
                source_id,
            )

        return _DELAYED_TTL_SECONDS
