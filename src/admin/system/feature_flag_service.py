"""
admin.system.feature_flag_service — In-process feature flag service.

Provides:
  - FeatureFlagService: in-process dict cache backed by DB + Redis pub/sub.
  - is_enabled: default True for unknown workflow flags, False for social_* flags.
  - set_enabled: persist to DB + publish Redis pub/sub + update cache.
  - reload: reload all flags from DB for the current environment.

Redis pub/sub channel: "feature_flags_updated"

PLAN-F-030 TASK-007
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

PUBSUB_CHANNEL = "feature_flags_updated"

# Flags that default to False when not found in DB/cache (D8: social sources)
_SOCIAL_FLAG_PREFIX = "social_"

# Flags that default to True when not found
_DEFAULT_ENABLED_FLAGS = {
    "realtime_mode",
    "morning_brief",
    "watchlist_scan",
    "earnings_risk_brief",
    "event_deep_dive",
}


def _default_for_unknown(flag_id: str) -> bool:
    """Return the default enabled state for a flag not in the DB/cache."""
    if flag_id.startswith(_SOCIAL_FLAG_PREFIX):
        return False
    return True


class FeatureFlagService:
    """In-process feature flag cache with Redis pub/sub invalidation.

    Args:
        flag_repo: IFeatureFlagRepository — DB access.
        redis: An async redis.asyncio.Redis client (for pub/sub).
        environment: The current deployment environment (e.g. "production").
    """

    def __init__(self, flag_repo, redis, environment: str) -> None:
        self._flag_repo = flag_repo
        self._redis = redis
        self._environment = environment
        # In-process cache: (flag_id, environment) -> bool
        self._cache: dict[tuple[str, str], bool] = {}

    async def reload(self) -> None:
        """Reload all flags from DB for the current environment."""
        flags = await self._flag_repo.list_all(self._environment)
        for flag in flags:
            self._cache[(flag.flag_id, flag.environment)] = flag.enabled
        logger.debug(
            "FeatureFlagService.reload: loaded %d flags for env=%r",
            len(flags),
            self._environment,
        )

    def is_enabled(self, flag_id: str, environment: Optional[str] = None) -> bool:
        """Return True if the flag is enabled.

        Checks in-process cache first. Falls back to _default_for_unknown.

        Args:
            flag_id: The flag identifier.
            environment: Environment to check. Defaults to self._environment.
        """
        env = environment or self._environment
        key = (flag_id, env)
        if key in self._cache:
            return self._cache[key]
        default = _default_for_unknown(flag_id)
        logger.debug(
            "FeatureFlagService.is_enabled: cache miss for %r/%r → default=%s",
            flag_id,
            env,
            default,
        )
        return default

    async def set_enabled(
        self,
        flag_id: str,
        enabled: bool,
        updated_by: uuid.UUID,
        environment: Optional[str] = None,
    ) -> None:
        """Persist flag state to DB, update local cache, publish pub/sub.

        Args:
            flag_id: The flag identifier.
            enabled: New enabled state.
            updated_by: UUID of the admin making the change.
            environment: Environment to update. Defaults to self._environment.
        """
        env = environment or self._environment

        # Persist to DB
        await self._flag_repo.set_enabled(
            flag_id=flag_id,
            environment=env,
            enabled=enabled,
            updated_by=updated_by,
        )

        # Update local cache
        self._cache[(flag_id, env)] = enabled

        # Publish pub/sub notification
        try:
            message = f"{flag_id}:{env}:{int(enabled)}"
            await self._redis.publish(PUBSUB_CHANNEL, message)
            logger.info(
                "FeatureFlagService: published %r to %r",
                message,
                PUBSUB_CHANNEL,
            )
        except Exception as exc:
            logger.warning(
                "FeatureFlagService: pub/sub publish failed: %s", exc
            )
