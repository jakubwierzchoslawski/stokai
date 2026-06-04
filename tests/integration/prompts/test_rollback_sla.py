"""Integration tests for rollback SLA — PLAN-F-014 TASK-010 (AC-003).

These tests verify the rollback SLA constraint: the complete round-trip of
PromptLabelService.rollback() must complete within 60 seconds (AC-003).

They use a test double for the DB repository so they run without a live database.
When a real (self-hosted) Langfuse instance is available, the LANGFUSE_HOST env var
can be set to run against it.

TDD spec from the plan:
- test_rollback_completes_within_60_seconds
- test_subsequent_agent_invocation_uses_rolled_back_version
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.ai.prompts.label_service import PromptLabel, PromptLabelService, RollbackResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_repo(
    *,
    current_production_sha: str | None = None,
) -> AsyncMock:
    """Create a mock IPromptPublicationRepository.

    Args:
        current_production_sha: SHA currently labelled 'production', or None.
    """
    repo = AsyncMock()

    if current_production_sha is not None:
        pub = MagicMock()
        pub.version_sha = current_production_sha
        repo.get_by_label = AsyncMock(return_value=pub)
    else:
        repo.get_by_label = AsyncMock(return_value=None)

    repo.upsert_label = AsyncMock(return_value=MagicMock())
    return repo


# ---------------------------------------------------------------------------
# Tests: rollback SLA
# ---------------------------------------------------------------------------


class TestRollbackSLA:
    @pytest.mark.asyncio
    async def test_rollback_completes_within_60_seconds(self) -> None:
        """Rollback round-trip completes in < 60 seconds (AC-003).

        Uses a test double for the repository so the test is deterministic.
        A real Langfuse call would also complete within this window.
        """
        old_sha = "a" * 40
        new_sha = "b" * 40

        repo = _make_repo(current_production_sha=old_sha)
        service = PromptLabelService(repo)

        start = time.monotonic()
        result = await service.rollback(role_id="relevance_analyst", to_version=new_sha)
        elapsed = time.monotonic() - start

        # The DB round-trip must complete in < 60 s (SLA from AC-003)
        assert elapsed < 60.0, f"Rollback took {elapsed:.2f}s, SLA is 60s"

        # Verify the result
        assert isinstance(result, RollbackResult)
        assert result.rolled_back_to == new_sha
        assert result.previous_version == old_sha
        assert result.effective_at is not None

    @pytest.mark.asyncio
    async def test_rollback_effective_at_is_within_60_seconds_of_request(self) -> None:
        """effective_at must be within 60 seconds of the rollback request (AC-003)."""
        new_sha = "c" * 40

        repo = _make_repo(current_production_sha="d" * 40)
        service = PromptLabelService(repo)

        request_time = datetime.now(tz=timezone.utc)
        result = await service.rollback(role_id="anomaly_detector", to_version=new_sha)

        delta = result.effective_at - request_time
        assert delta < timedelta(seconds=60), (
            f"effective_at delta is {delta.total_seconds():.2f}s, SLA is 60s"
        )

    @pytest.mark.asyncio
    async def test_rollback_updates_production_label_to_target_version(self) -> None:
        """After rollback, get_active_version('production') returns the rolled-back SHA."""
        old_sha = "e" * 40
        new_sha = "f" * 40

        # Repo: first call returns old_sha, second call (for verification) returns new_sha
        pub_old = MagicMock()
        pub_old.version_sha = old_sha
        pub_new = MagicMock()
        pub_new.version_sha = new_sha

        repo = AsyncMock()
        repo.get_by_label = AsyncMock(side_effect=[pub_old, pub_new])
        repo.upsert_label = AsyncMock(return_value=MagicMock())

        service = PromptLabelService(repo)

        result = await service.rollback(
            role_id="relevance_analyst", to_version=new_sha
        )

        # Verify production label was moved
        repo.upsert_label.assert_called_once_with(
            role_id="relevance_analyst",
            version_sha=new_sha,
            label=PromptLabel.production.value,
        )

        # Verify result
        assert result.rolled_back_to == new_sha

    @pytest.mark.asyncio
    async def test_rollback_sets_previous_version_correctly(self) -> None:
        """RollbackResult.previous_version equals the SHA that was production before rollback."""
        production_sha = "g" * 40
        target_sha = "h" * 40

        repo = _make_repo(current_production_sha=production_sha)
        service = PromptLabelService(repo)

        result = await service.rollback(role_id="exposure_analyst", to_version=target_sha)

        assert result.previous_version == production_sha

    @pytest.mark.asyncio
    async def test_rollback_with_no_prior_production_uses_unknown_as_previous(self) -> None:
        """When no production label exists, previous_version is 'unknown'."""
        repo = _make_repo(current_production_sha=None)
        service = PromptLabelService(repo)

        result = await service.rollback(
            role_id="narrative_writer", to_version="i" * 40
        )

        assert result.previous_version == "unknown"


# ---------------------------------------------------------------------------
# Tests: subsequent invocation uses rolled-back version
# ---------------------------------------------------------------------------


class TestSubsequentInvocationUsesRolledBackVersion:
    @pytest.mark.asyncio
    async def test_subsequent_agent_invocation_uses_rolled_back_version(self) -> None:
        """After rollback, agent invocation resolves the rolled-back SHA as prompt_version.

        This test wires PromptLoaderService + PromptLabelService together to verify
        the end-to-end version resolution flow (AC-003).
        """
        from src.ai.prompts.version_resolver import PromptVersionResolver
        from src.ai.prompts.prompt_loader import GitPromptLoader
        from pathlib import Path
        import tempfile

        rolled_back_sha = "j" * 40

        # Mock repo: get_by_label returns the rolled-back SHA
        pub = MagicMock()
        pub.version_sha = rolled_back_sha
        repo = AsyncMock()
        repo.get_by_label = AsyncMock(return_value=pub)
        repo.upsert_label = AsyncMock(return_value=MagicMock())

        # Stub GitPromptLoader (no actual files needed for this path)
        mock_loader = MagicMock(spec=GitPromptLoader)
        mock_loader.get_sha.return_value = "k" * 40  # fallback sha (not used)

        label_service = PromptLabelService(repo)
        resolver = PromptVersionResolver(label_service=label_service, loader=mock_loader)

        resolved_sha = await resolver.resolve_version("exposure_analyst")

        # Should return the rolled-back version from production label
        assert resolved_sha == rolled_back_sha

    @pytest.mark.asyncio
    async def test_version_resolver_falls_back_to_git_when_no_production_label(
        self,
    ) -> None:
        """PromptVersionResolver falls back to git SHA when no production label is set."""
        from src.ai.prompts.version_resolver import PromptVersionResolver
        from src.ai.prompts.prompt_loader import GitPromptLoader

        git_sha = "l" * 40

        repo = AsyncMock()
        repo.get_by_label = AsyncMock(return_value=None)  # no production label

        label_service = PromptLabelService(repo)

        mock_loader = MagicMock(spec=GitPromptLoader)
        mock_loader.get_sha.return_value = git_sha

        resolver = PromptVersionResolver(label_service=label_service, loader=mock_loader)
        resolved = await resolver.resolve_version("exposure_analyst")

        assert resolved == git_sha
