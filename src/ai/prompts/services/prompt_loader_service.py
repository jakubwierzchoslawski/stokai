"""src.ai.prompts.services.prompt_loader_service — PromptLoaderService.

PLAN-F-014 TASK-002 (AC-002, AC-004).

Reads prompt .md files from the prompts/ directory tree, parses YAML frontmatter,
computes git blob SHAs, and publishes to Langfuse.

Replaces the dataclass-based GitPromptLoader for code that needs Pydantic PromptFile.
The legacy GitPromptLoader is preserved for backward compatibility.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

from src.ai.prompts.schemas.prompt_schemas import (
    PromptFile,
    PromptFrontmatter,
    PromptLabel,
    PromptPublication,
)

logger = logging.getLogger(__name__)

# Module-level SHA cache shared across all PromptLoaderService instances
_sha_cache: dict[str, str] = {}

# Regex to extract YAML frontmatter block from .md files
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class PromptNotFoundError(FileNotFoundError):
    """Raised when no prompt file is found for the given role_id."""

    def __init__(self, role_id: str, prompts_root: Path) -> None:
        super().__init__(f"No prompt file found for role_id={role_id!r} under {prompts_root}")
        self.role_id = role_id


class LangfusePublishError(RuntimeError):
    """Raised when the Langfuse SDK call fails during publish_to_langfuse()."""

    def __init__(self, role_id: str, cause: Exception) -> None:
        super().__init__(f"Failed to publish prompt role_id={role_id!r} to Langfuse: {cause}")
        self.role_id = role_id
        self.cause = cause


class PromptLoaderService:
    """Loads prompt markdown files, parses YAML frontmatter, and publishes to Langfuse.

    Args:
        prompts_root: Root of the prompts directory (contains agents/, evaluators/, classifiers/).
        langfuse_client: Initialised Langfuse client, or None to skip publishing.
        repository: IPromptPublicationRepository for DB writes, or None to skip DB.
        published_by: Actor label for audit rows — 'ci' | 'cli' | 'admin'.
    """

    def __init__(
        self,
        prompts_root: Path,
        langfuse_client: object | None = None,
        repository: object | None = None,
        published_by: str = "ci",
    ) -> None:
        self._root = Path(prompts_root)
        self._langfuse_client = langfuse_client
        self._repository = repository
        self._published_by = published_by
        self._sha_cache = _sha_cache

    # ------------------------------------------------------------------
    # IPromptLoader contract
    # ------------------------------------------------------------------

    def load_prompt(self, role_id: str) -> PromptFile:
        """Load a prompt file by role_id; parse frontmatter; compute git SHA.

        Args:
            role_id: Name of the prompt file without extension (e.g. "exposure_analyst").

        Returns:
            Populated PromptFile Pydantic model.

        Raises:
            PromptNotFoundError: If no matching .md file is found.
        """
        path = self._resolve_path(role_id)
        if path is None:
            raise PromptNotFoundError(role_id, self._root)

        raw = path.read_text(encoding="utf-8")
        frontmatter, body = self._parse_frontmatter(raw)
        sha = self.get_sha(role_id)

        return PromptFile(
            role_id=role_id,
            file_path=str(path.resolve()),
            frontmatter=frontmatter,
            body=body,
            sha=sha,
        )

    def get_sha(self, role_id: str) -> str:
        """Return the git blob SHA for the prompt file, using cache.

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
        """Push current file content to Langfuse with git SHA as version label.

        Args:
            role_id: Prompt role identifier.

        Returns:
            PromptPublication Pydantic model.

        Raises:
            PromptNotFoundError: If no file is found for the given role_id.
            LangfusePublishError: If the Langfuse SDK call fails.
        """
        prompt_file = self.load_prompt(role_id)
        sha = prompt_file.sha

        if self._langfuse_client is not None and os.environ.get("LANGFUSE_HOST"):
            try:
                self._langfuse_client.create_prompt(
                    name=role_id,
                    prompt=prompt_file.body,
                    labels=["staging"],
                    config={"version_sha": sha},
                )
                logger.info("Published prompt role_id=%s sha=%s...", role_id, sha[:8])
            except Exception as exc:
                raise LangfusePublishError(role_id, exc) from exc
        else:
            logger.warning(
                "Langfuse not configured — skipping publish for role_id=%s", role_id
            )

        pub = PromptPublication(
            publication_id=uuid4(),
            role_id=role_id,
            sha=sha,
            langfuse_version=sha,
            published_at=datetime.now(tz=timezone.utc),
            published_by=self._published_by,
        )

        if self._repository is not None:
            try:
                await self._repository.upsert_label(
                    role_id=role_id,
                    version_sha=sha,
                    label=PromptLabel.staging.value,
                    langfuse_version_id=sha,
                )
            except Exception:
                logger.exception("Failed to write DB publication for role_id=%s", role_id)

        return pub

    async def publish_all(self) -> list[PromptPublication]:
        """Publish all prompt files discovered in the prompts/ directory tree.

        Returns:
            List of PromptPublication records for each successfully published file.
        """
        results: list[PromptPublication] = []
        for md_file in sorted(self._root.rglob("*.md")):
            role_id = md_file.stem
            try:
                pub = await self.publish_to_langfuse(role_id)
                results.append(pub)
            except Exception:
                logger.exception("Failed to publish role_id=%s", role_id)
        return results

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

    def _parse_frontmatter(self, raw: str) -> tuple[PromptFrontmatter, str]:
        """Extract YAML frontmatter and body from a markdown string.

        Args:
            raw: Full file content.

        Returns:
            (PromptFrontmatter, body_text) tuple.
        """
        match = _FRONTMATTER_RE.match(raw)
        if match:
            yaml_text = match.group(1)
            body = raw[match.end():]
            try:
                data = yaml.safe_load(yaml_text) or {}
            except yaml.YAMLError:
                logger.warning("Failed to parse frontmatter YAML; using empty frontmatter")
                data = {}
            fm = PromptFrontmatter(
                version=data.get("version") or None,
                agent=data.get("agent", ""),
                description=data.get("description", ""),
            )
        else:
            # No frontmatter — derive minimal frontmatter from filename
            fm = PromptFrontmatter(agent="", description="")
            body = raw
        return fm, body

    def _compute_sha(self, role_id: str) -> str:
        """Compute the SHA for a role's prompt file using git hash-object."""
        if os.environ.get("PROMPT_SHA_FALLBACK", "").lower() == "true":
            return self._hashlib_sha(role_id)

        path = self._resolve_path(role_id)
        if path is None:
            return hashlib.sha1(role_id.encode()).hexdigest()

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
            return self._hashlib_sha(role_id)
        except (FileNotFoundError, OSError):
            logger.debug("git not available; using hashlib fallback for role_id=%s", role_id)
            return self._hashlib_sha(role_id)

    def _hashlib_sha(self, role_id: str) -> str:
        """Compute SHA using hashlib.sha1 on file content."""
        path = self._resolve_path(role_id)
        if path is None:
            return hashlib.sha1(role_id.encode()).hexdigest()
        content = path.read_bytes()
        return hashlib.sha1(content).hexdigest()
