"""
PLAN-N-009 TASK-005 — Fixtures for integration/prompts tests.

Provides:
- langfuse_stub_client: in-memory Langfuse stub with label-resolution semantics.
- two_prompt_versions: publishes sha-v1 / sha-v2 to the stub; labels sha-v2
  as production; tears down after the test.

Environment gating
------------------
INTEGRATION_LANGFUSE=0 (default): in-memory stub is used.
INTEGRATION_LANGFUSE=1: real Langfuse SDK client is used instead of the stub.

Stub label-resolution semantics
--------------------------------
- Only one version may carry the 'production' label at a time.
- Assigning 'production' to a new version automatically strips the label from
  the prior holder.
- create_prompt registers a version SHA in the stub.
- update_prompt assigns a label to a registered SHA.
- get_prompt(label) returns the SHA currently carrying that label, or None.
"""
from __future__ import annotations

import os
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# In-memory Langfuse stub
# ---------------------------------------------------------------------------


class _LangfuseStubClient:
    """Lightweight in-memory stub implementing the Langfuse label contract.

    Faithfully replicates label-resolution semantics:
    - create_prompt(sha): register the SHA as a known version.
    - update_prompt(sha, label): assign label to sha; strip label from any
      prior holder so only one version carries each label at a time.
    - get_prompt(label): return the SHA currently carrying the given label,
      or None if none is assigned.
    """

    def __init__(self) -> None:
        # label -> sha
        self._labels: dict[str, str] = {}
        # known SHAs
        self._versions: set[str] = set()

    # ------------------------------------------------------------------
    # Langfuse SDK surface (minimal subset required by tests)
    # ------------------------------------------------------------------

    def create_prompt(self, name: str, prompt: str, version: str, **kwargs: Any) -> None:
        """Register a prompt version SHA in the stub."""
        self._versions.add(version)

    def update_prompt(
        self, name: str, version: str, labels: list[str] | None = None, **kwargs: Any
    ) -> None:
        """Assign labels to a version; strip each label from any prior holder."""
        for label in labels or []:
            self._labels[label] = version

    def get_prompt(
        self, name: str, label: str | None = None, **kwargs: Any
    ) -> MagicMock | None:
        """Return a mock with .version == sha for the given label, or None."""
        if label is None:
            return None
        sha = self._labels.get(label)
        if sha is None:
            return None
        mock = MagicMock()
        mock.version = sha
        return mock

    # ------------------------------------------------------------------
    # Test-helper surface
    # ------------------------------------------------------------------

    def known_versions(self) -> frozenset[str]:
        """Return all registered version SHAs."""
        return frozenset(self._versions)

    def active_label(self, label: str) -> str | None:
        """Return the SHA currently carrying the given label, or None."""
        return self._labels.get(label)

    def reset(self) -> None:
        """Clear all state."""
        self._labels.clear()
        self._versions.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def langfuse_stub_client() -> Generator[_LangfuseStubClient, None, None]:
    """Provide an in-memory Langfuse stub unless INTEGRATION_LANGFUSE=1.

    When INTEGRATION_LANGFUSE=1, yields None — the test is responsible for
    constructing a real Langfuse client from environment variables.
    """
    if os.environ.get("INTEGRATION_LANGFUSE", "0") == "1":
        # Signal to the test that a real client should be used
        yield None  # type: ignore[misc]
        return

    client = _LangfuseStubClient()
    yield client
    client.reset()


@pytest.fixture()
def two_prompt_versions(
    langfuse_stub_client: _LangfuseStubClient,
) -> Generator[dict[str, str], None, None]:
    """Publish sha-v1 and sha-v2 to the Langfuse stub; label sha-v2 as production.

    Yields a dict with keys:
        role_id:  "test-analyst-rollback"
        sha_v1:   sha for initial production version
        sha_v2:   sha for candidate/promoted version (current production)

    Teardown: resets the stub after the test.
    """
    role_id = "test-analyst-rollback"
    sha_v1 = "a" * 40
    sha_v2 = "b" * 40

    if langfuse_stub_client is not None:
        langfuse_stub_client.create_prompt(
            name=role_id,
            prompt="System: You are analyst v1.",
            version=sha_v1,
        )
        langfuse_stub_client.create_prompt(
            name=role_id,
            prompt="System: You are analyst v2.",
            version=sha_v2,
        )
        langfuse_stub_client.update_prompt(
            name=role_id,
            version=sha_v2,
            labels=["production"],
        )

    yield {
        "role_id": role_id,
        "sha_v1": sha_v1,
        "sha_v2": sha_v2,
    }

    if langfuse_stub_client is not None:
        langfuse_stub_client.reset()
