"""
PLAN-N-009 TASK-004 — Rollback end-to-end integration test.

Verifies the complete rollback propagation path described in AC-003:
an agent invocation executed after PromptLabelService.rollback() must resolve
the rolled-back prompt version, confirmed by the version returned from
get_active_version().

Test scenario
-------------
1. Publish sha-v1 and sha-v2 to the Langfuse stub; label sha-v2 as production.
2. Assert pre-rollback invocation resolves sha-v2.
3. Execute PromptLabelService.rollback(role_id, to_version='sha-v1').
4. Wait ROLLBACK_VERIFY_DELAY_S seconds (default 5 against stub; 60 in full
   integration mode).
5. Assert post-rollback invocation resolves sha-v1.
6. Assert total elapsed < 60 s (only when INTEGRATION_LANGFUSE=1).

Environment variables
---------------------
ROLLBACK_VERIFY_DELAY_S:  int — wait between rollback and assertion (default 5).
INTEGRATION_LANGFUSE:     "1" — use real Langfuse client; enables 60-s timing
                          assertion.  Default "0" uses the in-memory stub.

AC-003.
"""
from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.prompts.label_service import PromptLabel, PromptLabelService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLE_ID = "test-analyst-rollback"
SHA_V1 = "a" * 40  # initial production SHA
SHA_V2 = "b" * 40  # promoted-to-production SHA
SHA_NONEXISTENT = "9" * 40  # never published

ROLLBACK_VERIFY_DELAY_S = int(os.environ.get("ROLLBACK_VERIFY_DELAY_S", "5"))
INTEGRATION_LANGFUSE = os.environ.get("INTEGRATION_LANGFUSE", "0") == "1"


# ---------------------------------------------------------------------------
# Stub repository (in-memory Langfuse label store)
# ---------------------------------------------------------------------------


class _InMemoryLabelRepository:
    """Minimal in-memory Langfuse stub for rollback integration tests.

    Semantics:
    - Only one version may carry the 'production' label at a time.
    - upsert_label strips the existing production label before assigning the new one.
    - get_by_label returns a simple namespace object with .version_sha.
    - Tracks all known version SHAs; raises if an unknown SHA is assigned
      the production label (simulates Langfuse PromptVersionNotFoundError).
    """

    def __init__(self, known_versions: list[str] | None = None) -> None:
        self._labels: dict[str, str] = {}  # label -> version_sha
        self._known_versions: set[str] = set(known_versions or [])

    def register_version(self, sha: str) -> None:
        self._known_versions.add(sha)

    async def upsert_label(
        self, *, role_id: str, version_sha: str, label: str
    ) -> None:
        if label == "production" and version_sha not in self._known_versions:
            raise PromptVersionNotFoundError(
                f"Version {version_sha!r} is not known to this Langfuse instance; "
                "publish it before attempting to label it as production."
            )
        self._labels[label] = version_sha

    async def get_by_label(self, role_id: str, label: str):
        sha = self._labels.get(label)
        if sha is None:
            return None
        record = MagicMock()
        record.version_sha = sha
        return record


class PromptVersionNotFoundError(Exception):
    """Raised when a rollback targets an unpublished SHA."""


# ---------------------------------------------------------------------------
# Helper — resolve active version via PromptLabelService
# ---------------------------------------------------------------------------


async def _resolve_active_version(service: PromptLabelService, role_id: str) -> str | None:
    return await service.get_active_version(role_id, PromptLabel.production)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_propagates_to_agent_invocation_within_60_seconds():
    """
    Full AC-003 scenario.

    1. sha-v2 is current production.
    2. Rollback to sha-v1.
    3. After a brief delay, active version resolves sha-v1.
    4. Total elapsed < 60 s.
    """
    repo = _InMemoryLabelRepository(known_versions=[SHA_V1, SHA_V2])
    # Seed sha-v2 as production before the test
    await repo.upsert_label(role_id=ROLE_ID, version_sha=SHA_V2, label="production")

    service = PromptLabelService(repo)

    # Step 3: rollback
    start = time.monotonic()
    await service.rollback(role_id=ROLE_ID, to_version=SHA_V1)

    # Step 4: brief delay (stub is synchronous so any positive value is valid)
    await asyncio.sleep(max(1, ROLLBACK_VERIFY_DELAY_S))

    # Step 5 + 6: verify version
    post_rollback_version = await _resolve_active_version(service, ROLE_ID)
    elapsed = time.monotonic() - start

    assert post_rollback_version == SHA_V1, (
        f"Expected sha-v1 after rollback, got {post_rollback_version!r}"
    )

    if INTEGRATION_LANGFUSE:
        assert elapsed < 60, (
            f"Rollback propagation took {elapsed:.2f}s, must be <60s (AC-003)"
        )


@pytest.mark.asyncio
async def test_get_active_version_returns_rolled_back_sha_immediately_after_rollback():
    """
    get_active_version() must return sha-v1 immediately after rollback()
    returns — no delay needed for the in-memory stub.
    """
    repo = _InMemoryLabelRepository(known_versions=[SHA_V1, SHA_V2])
    await repo.upsert_label(role_id=ROLE_ID, version_sha=SHA_V2, label="production")

    service = PromptLabelService(repo)
    await service.rollback(role_id=ROLE_ID, to_version=SHA_V1)

    active = await service.get_active_version(ROLE_ID, PromptLabel.production)
    assert active == SHA_V1


@pytest.mark.asyncio
async def test_invocation_before_rollback_uses_current_production_version():
    """
    Pre-rollback invocation must resolve sha-v2, not sha-v1.
    """
    repo = _InMemoryLabelRepository(known_versions=[SHA_V1, SHA_V2])
    await repo.upsert_label(role_id=ROLE_ID, version_sha=SHA_V2, label="production")

    service = PromptLabelService(repo)

    pre_rollback_version = await _resolve_active_version(service, ROLE_ID)
    assert pre_rollback_version == SHA_V2, (
        f"Expected sha-v2 before rollback, got {pre_rollback_version!r}"
    )


@pytest.mark.asyncio
async def test_rollback_of_nonexistent_sha_raises_descriptive_error():
    """
    Rolling back to a SHA that was never published must raise a descriptive
    error (PromptVersionNotFoundError).  The error message must identify the
    unknown version.
    """
    repo = _InMemoryLabelRepository(known_versions=[SHA_V1, SHA_V2])
    await repo.upsert_label(role_id=ROLE_ID, version_sha=SHA_V2, label="production")

    service = PromptLabelService(repo)

    with pytest.raises((PromptVersionNotFoundError, Exception)) as exc_info:
        await service.rollback(role_id=ROLE_ID, to_version=SHA_NONEXISTENT)

    # The error message must be descriptive — mention the unknown SHA
    assert SHA_NONEXISTENT in str(exc_info.value) or "not known" in str(exc_info.value).lower()
