"""src.ai.prompts.prompt_loader — filesystem-based prompt loader with git SHA versioning.

PLAN-F-014 TASK-002 (AC-001, AC-002).

GitPromptLoader:
- Scans prompts/ directory tree for <role_id>.md files
- Returns PromptFile with content and git blob SHA
- SHA is cached to avoid repeated subprocess calls
- Falls back to hashlib.sha1 when git is unavailable or PROMPT_SHA_FALLBACK=true
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes (public contracts)
# ---------------------------------------------------------------------------


@dataclass
class PromptFile:
    role_id: str        # e.g. "exposure-analyst"
    path: str           # absolute path to .md file
    content: str        # full markdown content
    sha: str            # git blob SHA (hash-object) or hashlib fallback


@dataclass
class PromptPublication:
    role_id: str
    version_sha: str
    langfuse_version_id: str | None
    published_at: datetime


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class IPromptLoader(Protocol):
    def load_prompt(self, role_id: str) -> PromptFile: ...
    def get_sha(self, role_id: str) -> str: ...
    async def publish_to_langfuse(self, role_id: str) -> PromptPublication: ...
    async def publish_all(self) -> list[PromptPublication]: ...


# ---------------------------------------------------------------------------
# GitPromptLoader
# ---------------------------------------------------------------------------

# Module-level SHA cache shared across all GitPromptLoader instances
_sha_cache: dict[str, str] = {}


class GitPromptLoader:
    """Loads prompt markdown files from the prompts/ directory tree and computes
    git blob SHAs for versioning.

    Args:
        prompts_root: Root of the prompts directory (contains agents/, evaluators/, classifiers/).
    """

    def __init__(self, prompts_root: Path) -> None:
        self._root = Path(prompts_root)
        # Instance-level cache reference (shares module-level dict)
        self._sha_cache = _sha_cache

    # ------------------------------------------------------------------
    # IPromptLoader contract
    # ------------------------------------------------------------------

    def load_prompt(self, role_id: str) -> PromptFile:
        """Load a prompt file by role_id, scanning all subdirectories.

        Args:
            role_id: Name of the prompt file without extension (e.g. "exposure_analyst").

        Returns:
            PromptFile with content and SHA.

        Raises:
            FileNotFoundError: If no matching .md file is found.
        """
        target = f"{role_id}.md"
        for md_file in self._root.rglob("*.md"):
            if md_file.name == target:
                content = md_file.read_text(encoding="utf-8")
                sha = self.get_sha(role_id)
                return PromptFile(
                    role_id=role_id,
                    path=str(md_file.resolve()),
                    content=content,
                    sha=sha,
                )
        raise FileNotFoundError(
            f"No prompt file found for role_id={role_id!r} under {self._root}"
        )

    def get_sha(self, role_id: str) -> str:
        """Return the git blob SHA for the prompt file, using cache.

        Uses ``git hash-object`` to compute the SHA. Falls back to
        ``hashlib.sha1`` if git is unavailable or PROMPT_SHA_FALLBACK=true.

        Args:
            role_id: Prompt role identifier.

        Returns:
            40-character hex SHA string.
        """
        if role_id in self._sha_cache:
            return self._sha_cache[role_id]

        sha = self._compute_sha(role_id)
        self._sha_cache[role_id] = sha
        return sha

    async def publish_to_langfuse(self, role_id: str) -> PromptPublication:
        """Stub — actual publishing implemented by LangfusePromptPublisher."""
        raise NotImplementedError(
            "Use LangfusePromptPublisher for Langfuse publishing"
        )

    async def publish_all(self) -> list[PromptPublication]:
        """Stub — actual publishing implemented by LangfusePromptPublisher."""
        raise NotImplementedError(
            "Use LangfusePromptPublisher for Langfuse publishing"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, role_id: str) -> Path | None:
        """Find the .md file path for a given role_id, or None."""
        target = f"{role_id}.md"
        for md_file in self._root.rglob("*.md"):
            if md_file.name == target:
                return md_file
        return None

    def _compute_sha(self, role_id: str) -> str:
        """Compute the SHA for a role's prompt file.

        Order of preference:
        1. hashlib fallback if PROMPT_SHA_FALLBACK=true
        2. git hash-object subprocess
        3. hashlib.sha1 fallback on subprocess error
        """
        # Check environment override first
        if os.environ.get("PROMPT_SHA_FALLBACK", "").lower() == "true":
            return self._hashlib_sha(role_id)

        path = self._resolve_path(role_id)
        if path is None:
            # File doesn't exist yet; compute from empty string
            return hashlib.sha1(b"").hexdigest()

        try:
            result = subprocess.run(
                ["git", "hash-object", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            sha = result.stdout.strip()
            if sha and len(sha) == 40:
                return sha
            # git returned unexpected output; fall back
            return self._hashlib_sha(role_id)
        except (FileNotFoundError, OSError):
            logger.debug("git not available for SHA computation; using hashlib fallback")
            return self._hashlib_sha(role_id)

    def _hashlib_sha(self, role_id: str) -> str:
        """Compute SHA using hashlib.sha1 on file content."""
        path = self._resolve_path(role_id)
        if path is None:
            return hashlib.sha1(role_id.encode()).hexdigest()
        content = path.read_bytes()
        return hashlib.sha1(content).hexdigest()
