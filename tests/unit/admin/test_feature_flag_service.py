"""
Unit tests for FeatureFlagService.

PLAN-F-030 TASK-007
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.admin.system.feature_flag_service import FeatureFlagService
from src.storage.models.feature_flag import FeatureFlag


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_flag(flag_id: str, environment: str, enabled: bool) -> MagicMock:
    flag = MagicMock(spec=FeatureFlag)
    flag.flag_id = flag_id
    flag.environment = environment
    flag.enabled = enabled
    return flag


def _make_flag_repo(flags: list[MagicMock] | None = None) -> AsyncMock:
    repo = AsyncMock()
    flags = flags or []

    async def list_all(environment: str) -> list:
        return [f for f in flags if f.environment == environment]

    repo.list_all = AsyncMock(side_effect=list_all)
    repo.set_enabled = AsyncMock()
    return repo


def _make_redis() -> MagicMock:
    redis = MagicMock()
    redis.publish = AsyncMock()
    return redis


def _make_service(
    flags: list[MagicMock] | None = None,
    environment: str = "production",
) -> tuple[FeatureFlagService, AsyncMock, MagicMock]:
    flag_repo = _make_flag_repo(flags or [])
    redis = _make_redis()
    service = FeatureFlagService(flag_repo, redis, environment)
    return service, flag_repo, redis


# ── is_enabled ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestIsEnabled:
    async def test_is_enabled_morning_brief_true_after_reload(self) -> None:
        """is_enabled('morning_brief', 'production') → True after loading True flag."""
        flag = _make_flag("morning_brief", "production", True)
        service, _, _ = _make_service(flags=[flag])

        await service.reload()
        assert service.is_enabled("morning_brief", "production") is True

    async def test_is_enabled_social_twitter_false_after_reload(self) -> None:
        """is_enabled('social_twitter', 'production') → False after loading False flag."""
        flag = _make_flag("social_twitter", "production", False)
        service, _, _ = _make_service(flags=[flag])

        await service.reload()
        assert service.is_enabled("social_twitter", "production") is False

    async def test_is_enabled_unknown_flag_returns_true_default(self) -> None:
        """is_enabled('unknown', 'production') → True (non-social default)."""
        service, _, _ = _make_service(flags=[])
        assert service.is_enabled("unknown", "production") is True

    async def test_is_enabled_unknown_social_flag_returns_false_default(self) -> None:
        """is_enabled('social_unknown', 'production') → False (social default)."""
        service, _, _ = _make_service(flags=[])
        assert service.is_enabled("social_unknown", "production") is False


# ── set_enabled ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSetEnabled:
    async def test_set_enabled_persists_to_db(self) -> None:
        """set_enabled calls flag_repo.set_enabled."""
        flag = _make_flag("morning_brief", "production", True)
        service, flag_repo, _ = _make_service(flags=[flag])
        user_id = uuid.uuid4()

        await service.set_enabled("morning_brief", False, user_id, "production")

        flag_repo.set_enabled.assert_called_once_with(
            flag_id="morning_brief",
            environment="production",
            enabled=False,
            updated_by=user_id,
        )

    async def test_set_enabled_publishes_pubsub(self) -> None:
        """set_enabled publishes to Redis pub/sub channel."""
        flag = _make_flag("morning_brief", "production", True)
        service, _, redis = _make_service(flags=[flag])
        user_id = uuid.uuid4()

        await service.set_enabled("morning_brief", False, user_id, "production")

        redis.publish.assert_called_once()
        channel = redis.publish.call_args[0][0]
        assert channel == "feature_flags_updated"

    async def test_after_set_enabled_is_enabled_returns_updated_value(self) -> None:
        """After set_enabled, is_enabled returns the new value from cache."""
        flag = _make_flag("morning_brief", "production", True)
        service, _, _ = _make_service(flags=[flag])
        user_id = uuid.uuid4()

        await service.reload()
        assert service.is_enabled("morning_brief", "production") is True

        await service.set_enabled("morning_brief", False, user_id, "production")
        assert service.is_enabled("morning_brief", "production") is False


# ── reload ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReload:
    async def test_reload_updates_cache_from_db(self) -> None:
        """reload reads all flags and updates in-process cache."""
        flag1 = _make_flag("morning_brief", "production", False)
        flag2 = _make_flag("watchlist_scan", "production", True)
        service, _, _ = _make_service(flags=[flag1, flag2])

        await service.reload()

        assert service.is_enabled("morning_brief", "production") is False
        assert service.is_enabled("watchlist_scan", "production") is True


# ── Celery beat integration ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCeleryBeatIntegration:
    async def test_celery_beat_skips_task_when_flag_disabled(self) -> None:
        """When is_enabled returns False, a simulated Celery beat task skips execution."""
        flag = _make_flag("morning_brief", "production", False)
        service, _, _ = _make_service(flags=[flag])
        await service.reload()

        dispatched = []

        async def fake_celery_beat_morning_brief():
            if not service.is_enabled("morning_brief", "production"):
                return  # skip dispatch
            dispatched.append("dispatched")

        await fake_celery_beat_morning_brief()

        assert dispatched == []

    async def test_celery_beat_dispatches_when_flag_enabled(self) -> None:
        """When is_enabled returns True, a simulated Celery beat task proceeds."""
        flag = _make_flag("morning_brief", "production", True)
        service, _, _ = _make_service(flags=[flag])
        await service.reload()

        dispatched = []

        async def fake_celery_beat_morning_brief():
            if not service.is_enabled("morning_brief", "production"):
                return
            dispatched.append("dispatched")

        await fake_celery_beat_morning_brief()

        assert dispatched == ["dispatched"]
