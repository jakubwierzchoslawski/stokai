"""Tests for GitPromptLoader — TDD for PLAN-F-014 TASK-002."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ai.prompts.prompt_loader import GitPromptLoader, PromptFile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def prompts_base(tmp_path: Path) -> Path:
    """Create a minimal prompts directory tree for tests."""
    agents_dir = tmp_path / "prompts" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "exposure_analyst.md").write_text("# Exposure Analyst\n\n## System\nYou analyse exposure.\n")

    evaluators_dir = tmp_path / "prompts" / "evaluators"
    evaluators_dir.mkdir(parents=True)
    (evaluators_dir / "recommendation_judge.md").write_text("# Recommendation Judge\n\n## System\nYou judge recommendations.\n")

    return tmp_path


@pytest.fixture()
def loader(prompts_base: Path) -> GitPromptLoader:
    return GitPromptLoader(prompts_root=prompts_base / "prompts")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadPrompt:
    def test_load_prompt_returns_content_for_known_role_id(
        self, loader: GitPromptLoader
    ) -> None:
        pf = loader.load_prompt("exposure_analyst")
        assert isinstance(pf, PromptFile)
        assert pf.role_id == "exposure_analyst"
        assert "Exposure Analyst" in pf.content
        assert pf.path.endswith("exposure_analyst.md")

    def test_load_prompt_raises_FileNotFoundError_for_unknown_role(
        self, loader: GitPromptLoader
    ) -> None:
        with pytest.raises(FileNotFoundError):
            loader.load_prompt("nonexistent_role")

    def test_load_prompt_finds_nested_prompt(self, loader: GitPromptLoader) -> None:
        pf = loader.load_prompt("recommendation_judge")
        assert pf.role_id == "recommendation_judge"
        assert "Recommendation Judge" in pf.content


class TestGetSha:
    def test_get_sha_returns_40_char_hex_string(
        self, loader: GitPromptLoader
    ) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="da39a3ee5e6b4b0d3255bfef95601890afd80709\n",
            )
            sha = loader.get_sha("exposure_analyst")
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_get_sha_uses_cache_on_second_call(
        self, loader: GitPromptLoader
    ) -> None:
        """Subprocess must only be called once even if get_sha is called twice."""
        # Clear both module-level and instance-level cache to ensure fresh state
        loader._sha_cache.clear()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="da39a3ee5e6b4b0d3255bfef95601890afd80709\n",
            )
            sha1 = loader.get_sha("exposure_analyst")
            sha2 = loader.get_sha("exposure_analyst")

        assert sha1 == sha2
        # subprocess.run should have been called exactly once
        assert mock_run.call_count == 1

    def test_get_sha_uses_hashlib_when_PROMPT_SHA_FALLBACK_set(
        self, loader: GitPromptLoader, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        # Clear the cache so we don't get a cached git SHA
        loader._sha_cache.clear()

        with patch("subprocess.run") as mock_run:
            sha = loader.get_sha("exposure_analyst")
            # subprocess must NOT be called
            mock_run.assert_not_called()

        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_get_sha_falls_back_to_hashlib_on_subprocess_error(
        self, loader: GitPromptLoader
    ) -> None:
        loader._sha_cache.clear()
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            sha = loader.get_sha("exposure_analyst")

        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)
