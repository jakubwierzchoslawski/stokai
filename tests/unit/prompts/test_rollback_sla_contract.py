"""
PLAN-N-009 TASK-002 — Rollback SLA contract unit tests.

Verifies that PromptLabelService.rollback() returns a RollbackResult whose
effective_at is within the 60-second SLA window mandated by REQ-N-009 AC-003.

These tests mock the DB repository; they do not require a live Langfuse
instance.  The distinction from PLAN-F-014 TASK-010 tests is scope: these
tests verify the SLA observable to a caller, not implementation internals.

AC-003.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.prompts.label_service import PromptLabel, PromptLabelService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pub(version_sha: str = "a" * 40) -> MagicMock:
    pub = MagicMock()
    pub.version_sha = version_sha
    return pub


def _make_repo(
    *,
    current_sha: str | None = "a" * 40,
) -> AsyncMock:
    """Return an AsyncMock repository.

    current_sha: the value returned by get_by_label (None means no prior label).
    """
    repo = AsyncMock()
    if current_sha is not None:
        repo.get_by_label = AsyncMock(return_value=_make_pub(current_sha))
    else:
        repo.get_by_label = AsyncMock(return_value=None)
    repo.upsert_label = AsyncMock(return_value=MagicMock())
    return repo


# ---------------------------------------------------------------------------
# TASK-002 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_result_effective_at_is_populated():
    """After calling rollback(), result.effective_at must not be None."""
    repo = _make_repo()
    service = PromptLabelService(repo)

    result = await service.rollback(role_id="recommendation-analyst", to_version="b" * 40)

    assert result.effective_at is not None


@pytest.mark.asyncio
async def test_rollback_result_effective_at_is_within_60_seconds():
    """result.effective_at must be within 60 s of the call start time."""
    before = datetime.now(tz=timezone.utc)

    repo = _make_repo()
    service = PromptLabelService(repo)

    result = await service.rollback(role_id="recommendation-analyst", to_version="b" * 40)

    # effective_at must be after or equal to before
    assert result.effective_at >= before
    # effective_at must be within 60 s of before
    assert result.effective_at - before < timedelta(seconds=60)


@pytest.mark.asyncio
async def test_rollback_result_rolled_back_to_equals_requested_version():
    """result.rolled_back_to must equal the requested to_version SHA."""
    target_sha = "c" * 40

    repo = _make_repo()
    service = PromptLabelService(repo)

    result = await service.rollback(role_id="recommendation-analyst", to_version=target_sha)

    assert result.rolled_back_to == target_sha


@pytest.mark.asyncio
async def test_rollback_result_previous_version_is_captured():
    """When get_by_label returns sha-old, result.previous_version == sha-old."""
    old_sha = "d" * 40

    repo = _make_repo(current_sha=old_sha)
    service = PromptLabelService(repo)

    result = await service.rollback(role_id="recommendation-analyst", to_version="e" * 40)

    assert result.previous_version == old_sha


@pytest.mark.asyncio
async def test_rollback_returns_result_not_raises_on_no_prior_production_label():
    """When get_by_label returns None (no prior label), rollback must not raise.

    result.previous_version must be None or an empty string — not an exception.
    """
    repo = _make_repo(current_sha=None)
    service = PromptLabelService(repo)

    # Must not raise
    result = await service.rollback(role_id="new-analyst", to_version="f" * 40)

    assert result is not None
    # previous_version should be falsy (None, empty string, "unknown", etc.)
    assert not result.previous_version or result.previous_version in (None, "", "unknown")
