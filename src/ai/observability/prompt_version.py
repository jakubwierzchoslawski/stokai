"""
PromptVersionResolver — resolves git blob SHAs for prompt files.

Architecture §8: prompt SHA recorded as version label on every agent span.

The resolver shells out to ``git rev-parse HEAD:<path>`` and caches the result
per path to avoid repeated subprocess calls in a high-throughput run.

Fallback chain (in order):
1. ``git rev-parse HEAD:prompts/<path>`` subprocess.
2. PROMPT_SHA_FALLBACK environment variable (set at Docker build time).
3. Literal string ``'unknown'``.
"""
from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

# Module-level cache: prompt_path → resolved SHA
_sha_cache: dict[str, str] = {}


class PromptVersionResolver:
    """Resolve the git blob SHA for a prompt file path.

    Parameters
    ----------
    project_root:
        Absolute path to the project root that contains the ``.git`` directory.
        Defaults to the current working directory.
    """

    def __init__(self, project_root: str | None = None) -> None:
        self._project_root = project_root or os.getcwd()

    def resolve(self, prompt_path: str) -> str:
        """Return the git blob SHA for the given prompt file path.

        The path is interpreted relative to the project root (e.g.
        ``prompts/risk_analyst.yaml``).  The resolved SHA is cached on first
        call per path.

        Falls back to env var ``PROMPT_SHA_FALLBACK`` or ``'unknown'`` if not
        in a git repo or the path is absent.
        """
        if prompt_path in _sha_cache:
            return _sha_cache[prompt_path]

        sha = self._git_blob_sha(prompt_path)
        _sha_cache[prompt_path] = sha
        return sha

    def _git_blob_sha(self, prompt_path: str) -> str:
        """Shell out to git to resolve the blob SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", f"HEAD:{prompt_path}"],
                capture_output=True,
                text=True,
                cwd=self._project_root,
                timeout=5,
            )
            if result.returncode == 0:
                sha = result.stdout.strip()
                if sha:
                    return sha
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            logger.debug("git rev-parse failed for %r: %s", prompt_path, exc)

        # Fallback 1: env var baked in at build time
        fallback = os.environ.get("PROMPT_SHA_FALLBACK", "").strip()
        if fallback:
            logger.debug("Using PROMPT_SHA_FALLBACK=%r for %r", fallback, prompt_path)
            return fallback

        # Fallback 2: unknown
        logger.debug("Cannot resolve SHA for %r, returning 'unknown'", prompt_path)
        return "unknown"


def clear_sha_cache() -> None:
    """Clear the module-level SHA cache (test utility)."""
    _sha_cache.clear()
