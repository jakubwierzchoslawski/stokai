"""
Tests for PromptPublicationRepository — TDD for PLAN-F-014 TASK-003.

All DB interactions are mocked via AsyncMock. No real PostgreSQL required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.storage.repositories.prompt_publication_repository import (
    PromptPublicationRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pub_orm(
    role_id: str = "exposure_analyst",
    label: str = "production",
    version_sha: str = "a" * 40,
    langfuse_version_id: str | None = None,
    published_by: uuid.UUID | None = None,
    pub_id: uuid.UUID | None = None,
) -> MagicMock:
    """Return a MagicMock that mimics a PromptPublication ORM row."""
    row = MagicMock()
    row.pub_id = pub_id or uuid.uuid4()
    row.role_id = role_id
    row.label = label
    row.version_sha = version_sha
    row.langfuse_version_id = langfuse_version_id
    row.published_by = published_by
    row.published_at = datetime.now(tz=timezone.utc)
    return row


def _async_result(scalar_value):
    """Return an AsyncMock that returns scalar_value from scalar_one()."""
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=scalar_value)
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)
    return result


def _async_scalars_result(items: list):
    """Return an AsyncMock that returns items from scalars().all()."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=items)
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


# ---------------------------------------------------------------------------
# Tests: upsert_label
# ---------------------------------------------------------------------------


class TestUpsertLabel:
    @pytest.mark.asyncio
    async def test_upsert_creates_new_row(self) -> None:
        """upsert_label issues INSERT ... ON CONFLICT and returns the ORM object."""
        session = AsyncMock()
        pub = _make_pub_orm(version_sha="b" * 40, label="production")

        # First call (RETURNING pub_id), second call (SELECT by pub_id)
        session.execute = AsyncMock(
            side_effect=[
                _async_result(pub.pub_id),   # INSERT RETURNING
                _async_result(pub),           # SELECT by pub_id
            ]
        )

        repo = PromptPublicationRepository(session)
        result = await repo.upsert_label(
            role_id="exposure_analyst",
            version_sha="b" * 40,
            label="production",
        )

        assert result.role_id == "exposure_analyst"
        assert result.version_sha == "b" * 40
        assert result.label == "production"
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_label_version(self) -> None:
        """upsert_label with same (role_id, label) updates version_sha."""
        session = AsyncMock()
        old_sha = "a" * 40
        new_sha = "c" * 40
        updated_pub = _make_pub_orm(version_sha=new_sha, label="production")

        session.execute = AsyncMock(
            side_effect=[
                _async_result(updated_pub.pub_id),
                _async_result(updated_pub),
            ]
        )

        repo = PromptPublicationRepository(session)
        result = await repo.upsert_label(
            role_id="exposure_analyst",
            version_sha=new_sha,
            label="production",
        )

        assert result.version_sha == new_sha
        assert result.version_sha != old_sha

    @pytest.mark.asyncio
    async def test_upsert_with_langfuse_version_id(self) -> None:
        """upsert_label stores langfuse_version_id when provided."""
        session = AsyncMock()
        pub = _make_pub_orm(langfuse_version_id="lf-abc-123")

        session.execute = AsyncMock(
            side_effect=[
                _async_result(pub.pub_id),
                _async_result(pub),
            ]
        )

        repo = PromptPublicationRepository(session)
        result = await repo.upsert_label(
            role_id="exposure_analyst",
            version_sha="a" * 40,
            label="staging",
            langfuse_version_id="lf-abc-123",
        )

        assert result.langfuse_version_id == "lf-abc-123"


# ---------------------------------------------------------------------------
# Tests: get_by_label
# ---------------------------------------------------------------------------


class TestGetByLabel:
    @pytest.mark.asyncio
    async def test_get_by_label_returns_latest_for_production(self) -> None:
        """get_by_label returns the PromptPublication for (role_id, label)."""
        session = AsyncMock()
        pub = _make_pub_orm(label="production", version_sha="d" * 40)

        session.execute = AsyncMock(return_value=_async_result(pub))

        repo = PromptPublicationRepository(session)
        result = await repo.get_by_label("exposure_analyst", "production")

        assert result is not None
        assert result.label == "production"
        assert result.version_sha == "d" * 40

    @pytest.mark.asyncio
    async def test_get_by_label_returns_none_when_absent(self) -> None:
        """get_by_label returns None when no row exists for (role_id, label)."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_async_result(None))

        repo = PromptPublicationRepository(session)
        result = await repo.get_by_label("nonexistent_role", "production")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: list_history
# ---------------------------------------------------------------------------


class TestListHistory:
    @pytest.mark.asyncio
    async def test_list_history_ordered_by_published_at_desc(self) -> None:
        """list_history returns publications ordered by published_at descending."""
        session = AsyncMock()
        now = datetime.now(tz=timezone.utc)
        pub1 = _make_pub_orm(version_sha="e" * 40, label="production")
        pub1.published_at = now
        pub2 = _make_pub_orm(version_sha="f" * 40, label="staging")
        pub2.published_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        session.execute = AsyncMock(return_value=_async_scalars_result([pub1, pub2]))

        repo = PromptPublicationRepository(session)
        results = await repo.list_history("exposure_analyst")

        assert len(results) == 2
        # First item should be newest (pub1 > pub2)
        assert results[0].published_at >= results[1].published_at

    @pytest.mark.asyncio
    async def test_list_history_returns_empty_for_unknown_role(self) -> None:
        """list_history returns empty list when no rows exist for role_id."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_async_scalars_result([]))

        repo = PromptPublicationRepository(session)
        results = await repo.list_history("unknown_role")

        assert results == []
