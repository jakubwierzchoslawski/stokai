"""Tests for LangfusePromptPublisher — TDD for PLAN-F-014 TASK-004."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.prompts.langfuse_publisher import CANONICAL_ROLE_IDS, LangfusePromptPublisher
from src.ai.prompts.prompt_loader import GitPromptLoader, PromptFile, PromptPublication


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def prompts_base(tmp_path: Path) -> Path:
    """Create all 15 prompt stub files for tests."""
    for subdir, names in [
        (
            "agents",
            [
                "exposure_analyst",
                "historical_context",
                "anomaly_detector",
                "recommendation",
                "narrative_writer",
                "morning_brief_analyst",
                "watchlist_analyst",
                "earnings_analyst",
                "qa_analyst",
            ],
        ),
        ("evaluators", ["recommendation_judge", "factuality_judge", "calibration_judge"]),
        ("classifiers", ["event_classifier", "ticker_extractor", "sentiment_analyzer"]),
    ]:
        d = tmp_path / "prompts" / subdir
        d.mkdir(parents=True)
        for name in names:
            (d / f"{name}.md").write_text(f"# {name}\n\n## System\nYou are {name}.\n")
    return tmp_path


@pytest.fixture()
def loader(prompts_base: Path) -> GitPromptLoader:
    loader = GitPromptLoader(prompts_root=prompts_base / "prompts")
    loader._sha_cache.clear()
    return loader


@pytest.fixture()
def mock_repository() -> AsyncMock:
    repo = AsyncMock()
    pub = MagicMock(spec=["pub_id", "role_id", "label", "version_sha", "published_at"])
    repo.upsert_label = AsyncMock(return_value=pub)
    return repo


@pytest.fixture()
def mock_langfuse_client() -> MagicMock:
    client = MagicMock()
    prompt_obj = MagicMock()
    prompt_obj.id = "lf-version-abc-123"
    client.create_prompt = MagicMock(return_value=prompt_obj)
    return client


# ---------------------------------------------------------------------------
# Tests: publish_to_langfuse with client
# ---------------------------------------------------------------------------


class TestPublishToLangfuse:
    @pytest.mark.asyncio
    async def test_creates_prompt_via_langfuse_client(
        self,
        loader: GitPromptLoader,
        mock_repository: AsyncMock,
        mock_langfuse_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """publish_to_langfuse calls langfuse.create_prompt() when host is set."""
        monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse.local:3000")
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        loader._sha_cache.clear()

        publisher = LangfusePromptPublisher(
            loader=loader,
            repository=mock_repository,
            langfuse_client=mock_langfuse_client,
        )

        result = await publisher.publish_to_langfuse("exposure_analyst")

        assert isinstance(result, PromptPublication)
        assert result.role_id == "exposure_analyst"
        assert len(result.version_sha) == 40
        mock_langfuse_client.create_prompt.assert_called_once()
        call_kwargs = mock_langfuse_client.create_prompt.call_args
        assert call_kwargs.kwargs["name"] == "exposure_analyst" or call_kwargs.args[0] == "exposure_analyst" or call_kwargs.kwargs.get("name") == "exposure_analyst"

    @pytest.mark.asyncio
    async def test_publish_writes_to_db_repository(
        self,
        loader: GitPromptLoader,
        mock_repository: AsyncMock,
        mock_langfuse_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """publish_to_langfuse always writes the publication to DB."""
        monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse.local:3000")
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        loader._sha_cache.clear()

        publisher = LangfusePromptPublisher(
            loader=loader,
            repository=mock_repository,
            langfuse_client=mock_langfuse_client,
        )

        await publisher.publish_to_langfuse("exposure_analyst")

        mock_repository.upsert_label.assert_called_once()
        call_kwargs = mock_repository.upsert_label.call_args
        assert call_kwargs.kwargs.get("role_id") == "exposure_analyst" or call_kwargs.args[0] == "exposure_analyst"


# ---------------------------------------------------------------------------
# Tests: publish_all
# ---------------------------------------------------------------------------


class TestPublishAll:
    @pytest.mark.asyncio
    async def test_publish_all_covers_all_15_prompts(
        self,
        loader: GitPromptLoader,
        mock_repository: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """publish_all returns 15 PromptPublication objects."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        loader._sha_cache.clear()

        publisher = LangfusePromptPublisher(
            loader=loader,
            repository=mock_repository,
            langfuse_client=None,
        )

        results = await publisher.publish_all()

        assert len(results) == 15
        role_ids = {r.role_id for r in results}
        assert role_ids == set(CANONICAL_ROLE_IDS)

    @pytest.mark.asyncio
    async def test_publish_all_skips_langfuse_when_host_not_configured(
        self,
        loader: GitPromptLoader,
        mock_repository: AsyncMock,
        mock_langfuse_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When LANGFUSE_HOST is absent, langfuse_version_id is None in results."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        loader._sha_cache.clear()

        publisher = LangfusePromptPublisher(
            loader=loader,
            repository=mock_repository,
            langfuse_client=mock_langfuse_client,  # client present but host not set
        )

        results = await publisher.publish_all()

        # Langfuse client should not have been called
        mock_langfuse_client.create_prompt.assert_not_called()
        # All results should have langfuse_version_id = None
        assert all(r.langfuse_version_id is None for r in results)

    @pytest.mark.asyncio
    async def test_publish_all_with_no_langfuse_client_returns_none_version_ids(
        self,
        loader: GitPromptLoader,
        mock_repository: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When langfuse_client is None, langfuse_version_id is None for all."""
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        loader._sha_cache.clear()

        publisher = LangfusePromptPublisher(
            loader=loader,
            repository=mock_repository,
            langfuse_client=None,
        )

        results = await publisher.publish_all()

        assert len(results) == 15
        assert all(r.langfuse_version_id is None for r in results)
