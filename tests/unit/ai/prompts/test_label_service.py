"""Tests for PromptLabelService — TDD for PLAN-F-014 TASK-005."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.prompts.label_service import PromptLabel, PromptLabelService, RollbackResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pub(
    role_id: str = "exposure_analyst",
    label: str = "production",
    version_sha: str = "a" * 40,
) -> MagicMock:
    pub = MagicMock()
    pub.pub_id = uuid.uuid4()
    pub.role_id = role_id
    pub.label = label
    pub.version_sha = version_sha
    pub.published_at = datetime.now(tz=timezone.utc)
    return pub


def _make_repo(
    *,
    upsert_return: MagicMock | None = None,
    get_return: MagicMock | None = None,
) -> AsyncMock:
    repo = AsyncMock()
    repo.upsert_label = AsyncMock(return_value=upsert_return or MagicMock())
    repo.get_by_label = AsyncMock(return_value=get_return)
    return repo


# ---------------------------------------------------------------------------
# Tests: apply_label
# ---------------------------------------------------------------------------


class TestApplyLabel:
    @pytest.mark.asyncio
    async def test_apply_label_calls_upsert(self) -> None:
        """apply_label delegates to repository.upsert_label."""
        repo = _make_repo()
        service = PromptLabelService(repo)

        await service.apply_label(
            role_id="exposure_analyst",
            version_sha="b" * 40,
            label=PromptLabel.production,
        )

        repo.upsert_label.assert_called_once_with(
            role_id="exposure_analyst",
            version_sha="b" * 40,
            label="production",
        )

    @pytest.mark.asyncio
    async def test_apply_label_staging(self) -> None:
        """apply_label works for staging label."""
        repo = _make_repo()
        service = PromptLabelService(repo)

        await service.apply_label(
            role_id="narrative_writer",
            version_sha="c" * 40,
            label=PromptLabel.staging,
        )

        repo.upsert_label.assert_called_once()
        call_kwargs = repo.upsert_label.call_args.kwargs
        assert call_kwargs["label"] == "staging"


# ---------------------------------------------------------------------------
# Tests: get_active_version
# ---------------------------------------------------------------------------


class TestGetActiveVersion:
    @pytest.mark.asyncio
    async def test_get_active_version_returns_sha_for_production(self) -> None:
        """get_active_version returns version_sha when label exists."""
        sha = "d" * 40
        pub = _make_pub(version_sha=sha, label="production")
        repo = _make_repo(get_return=pub)
        service = PromptLabelService(repo)

        result = await service.get_active_version("exposure_analyst", PromptLabel.production)

        assert result == sha

    @pytest.mark.asyncio
    async def test_get_active_version_returns_none_when_no_label(self) -> None:
        """get_active_version returns None when no row exists for (role_id, label)."""
        repo = _make_repo(get_return=None)
        service = PromptLabelService(repo)

        result = await service.get_active_version("exposure_analyst", PromptLabel.production)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_version_queries_correct_label(self) -> None:
        """get_active_version passes the correct label string to repository."""
        repo = _make_repo(get_return=None)
        service = PromptLabelService(repo)

        await service.get_active_version("exposure_analyst", PromptLabel.canary)

        repo.get_by_label.assert_called_once_with("exposure_analyst", "canary")


# ---------------------------------------------------------------------------
# Tests: rollback
# ---------------------------------------------------------------------------


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_moves_production_label(self) -> None:
        """rollback upserts production label to the target version."""
        old_sha = "e" * 40
        new_sha = "f" * 40
        pub = _make_pub(version_sha=old_sha, label="production")
        repo = _make_repo(get_return=pub)
        service = PromptLabelService(repo)

        await service.rollback(role_id="exposure_analyst", to_version=new_sha)

        # upsert_label should be called with the new SHA and production label
        repo.upsert_label.assert_called_once_with(
            role_id="exposure_analyst",
            version_sha=new_sha,
            label="production",
        )

    @pytest.mark.asyncio
    async def test_rollback_returns_correct_previous_and_new_versions(self) -> None:
        """rollback returns RollbackResult with previous_version and rolled_back_to."""
        old_sha = "e" * 40
        new_sha = "f" * 40
        pub = _make_pub(version_sha=old_sha, label="production")
        repo = _make_repo(get_return=pub)
        service = PromptLabelService(repo)

        result = await service.rollback(role_id="exposure_analyst", to_version=new_sha)

        assert isinstance(result, RollbackResult)
        assert result.role_id == "exposure_analyst"
        assert result.previous_version == old_sha
        assert result.rolled_back_to == new_sha
        assert result.effective_at is not None

    @pytest.mark.asyncio
    async def test_rollback_succeeds_when_no_prior_production_label(self) -> None:
        """rollback uses 'unknown' as previous_version when no label existed."""
        new_sha = "f" * 40
        repo = _make_repo(get_return=None)  # no prior production label
        service = PromptLabelService(repo)

        result = await service.rollback(role_id="exposure_analyst", to_version=new_sha)

        assert result.previous_version == "unknown"
        assert result.rolled_back_to == new_sha

    @pytest.mark.asyncio
    async def test_rollback_does_not_require_langfuse(self) -> None:
        """Rollback succeeds without any Langfuse dependency (DB-only path)."""
        # Service has no Langfuse client at all — still works
        old_sha = "g" * 40
        new_sha = "h" * 40
        pub = _make_pub(version_sha=old_sha)
        repo = _make_repo(get_return=pub)
        # No langfuse client injected into service
        service = PromptLabelService(repo)

        result = await service.rollback(role_id="recommendation", to_version=new_sha)

        assert result.rolled_back_to == new_sha
