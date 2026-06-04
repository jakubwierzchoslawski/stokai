"""Tests for PromptVersionResolver — TDD for PLAN-F-014 TASK-009."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.prompts.label_service import PromptLabel, PromptLabelService
from src.ai.prompts.prompt_loader import GitPromptLoader
from src.ai.prompts.version_resolver import PromptVersionResolver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def loader(tmp_path: Path) -> GitPromptLoader:
    """Create a GitPromptLoader with a stub exposure_analyst.md."""
    agents_dir = tmp_path / "prompts" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "exposure_analyst.md").write_text("# Exposure Analyst\n\n## System\nYou analyse.")
    ldr = GitPromptLoader(prompts_root=tmp_path / "prompts")
    ldr._sha_cache.clear()
    return ldr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolveVersion:
    @pytest.mark.asyncio
    async def test_returns_production_sha_when_label_exists(
        self, loader: GitPromptLoader, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_version returns the production label SHA from the DB."""
        production_sha = "a" * 40

        mock_label_service = AsyncMock(spec=PromptLabelService)
        mock_label_service.get_active_version = AsyncMock(return_value=production_sha)

        resolver = PromptVersionResolver(
            label_service=mock_label_service,
            loader=loader,
        )

        result = await resolver.resolve_version("exposure_analyst")

        assert result == production_sha
        mock_label_service.get_active_version.assert_called_once_with(
            "exposure_analyst", PromptLabel.production
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_git_sha_when_no_label(
        self, loader: GitPromptLoader, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_version falls back to GitPromptLoader.get_sha when no label exists."""
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        loader._sha_cache.clear()

        mock_label_service = AsyncMock(spec=PromptLabelService)
        mock_label_service.get_active_version = AsyncMock(return_value=None)

        resolver = PromptVersionResolver(
            label_service=mock_label_service,
            loader=loader,
        )

        result = await resolver.resolve_version("exposure_analyst")

        assert len(result) == 40
        assert all(c in "0123456789abcdef" for c in result)
        # Label service was still consulted
        mock_label_service.get_active_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_production_label_takes_priority_over_git_sha(
        self, loader: GitPromptLoader
    ) -> None:
        """When production label exists, git SHA is NOT computed."""
        production_sha = "b" * 40

        mock_label_service = AsyncMock(spec=PromptLabelService)
        mock_label_service.get_active_version = AsyncMock(return_value=production_sha)

        # Spy on loader.get_sha to ensure it is NOT called
        original_get_sha = loader.get_sha
        called = []
        def spy_get_sha(role_id):
            called.append(role_id)
            return original_get_sha(role_id)
        loader.get_sha = spy_get_sha

        resolver = PromptVersionResolver(
            label_service=mock_label_service,
            loader=loader,
        )

        result = await resolver.resolve_version("exposure_analyst")

        assert result == production_sha
        assert called == [], "get_sha should NOT be called when production label exists"
