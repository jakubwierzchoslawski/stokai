"""src.ai.prompts.langfuse_publisher — LangfusePromptPublisher.

PLAN-F-014 TASK-004.

Publishes prompt files to the Langfuse prompt registry and records the
publication in the prompt_publication DB table.

If LANGFUSE_HOST is not set, publishing is skipped and a PromptPublication
with langfuse_version_id=None is returned (so the DB record is still written).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from src.ai.prompts.prompt_loader import GitPromptLoader, PromptPublication

logger = logging.getLogger(__name__)

# The 15 canonical prompt role IDs for this project
CANONICAL_ROLE_IDS: list[str] = [
    # Agents (9)
    "exposure_analyst",
    "historical_context",
    "anomaly_detector",
    "recommendation",
    "narrative_writer",
    "morning_brief_analyst",
    "watchlist_analyst",
    "earnings_analyst",
    "qa_analyst",
    # Evaluators (3)
    "recommendation_judge",
    "factuality_judge",
    "calibration_judge",
    # Classifiers (3)
    "event_classifier",
    "ticker_extractor",
    "sentiment_analyzer",
]


class LangfusePromptPublisher:
    """Publishes prompt files to Langfuse and records the publication in DB.

    Args:
        loader: GitPromptLoader instance for reading prompt files and SHAs.
        repository: PromptPublicationRepository instance for DB writes.
        langfuse_client: Initialised Langfuse client, or None to skip Langfuse.
    """

    def __init__(
        self,
        loader: GitPromptLoader,
        repository: Any,  # IPromptPublicationRepository
        langfuse_client: Any | None = None,
    ) -> None:
        self._loader = loader
        self._repository = repository
        self._langfuse_client = langfuse_client

    # ------------------------------------------------------------------
    # IPromptLoader contract (publishing methods)
    # ------------------------------------------------------------------

    async def publish_to_langfuse(self, role_id: str) -> PromptPublication:
        """Publish a single prompt to Langfuse and record it in the DB.

        If LANGFUSE_HOST is not set (or client is None), the publish step is
        skipped and langfuse_version_id is set to None. The DB record is
        always written.

        Args:
            role_id: Prompt role identifier (e.g. "exposure_analyst").

        Returns:
            PromptPublication with version_sha and optional langfuse_version_id.
        """
        prompt_file = self._loader.load_prompt(role_id)
        version_sha = prompt_file.sha
        langfuse_version_id: str | None = None

        if self._langfuse_client is None or not os.environ.get("LANGFUSE_HOST"):
            logger.warning(
                "LANGFUSE_HOST not configured — skipping Langfuse publish for role_id=%s",
                role_id,
            )
        else:
            langfuse_version_id = await self._publish_one(
                role_id=role_id,
                content=prompt_file.content,
                version_sha=version_sha,
            )

        # Always write to DB (best-effort logging)
        try:
            await self._repository.upsert_label(
                role_id=role_id,
                version_sha=version_sha,
                label="staging",  # Published versions land in staging by default
                langfuse_version_id=langfuse_version_id,
            )
        except Exception:
            logger.exception(
                "Failed to write prompt publication to DB for role_id=%s", role_id
            )

        return PromptPublication(
            role_id=role_id,
            version_sha=version_sha,
            langfuse_version_id=langfuse_version_id,
            published_at=datetime.now(tz=timezone.utc),
        )

    async def publish_all(self) -> list[PromptPublication]:
        """Publish all 15 canonical prompt files to Langfuse.

        Continues publishing remaining prompts even if one fails.

        Returns:
            List of PromptPublication objects (15 when all succeed).
        """
        results: list[PromptPublication] = []
        for role_id in CANONICAL_ROLE_IDS:
            try:
                pub = await self.publish_to_langfuse(role_id)
                results.append(pub)
                logger.info("Published prompt role_id=%s sha=%s...", role_id, pub.version_sha[:8])
            except Exception:
                logger.exception("Failed to publish prompt role_id=%s", role_id)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _publish_one(
        self, role_id: str, content: str, version_sha: str
    ) -> str | None:
        """Call the Langfuse create_prompt() API.

        Args:
            role_id: Prompt role identifier used as the Langfuse prompt name.
            content: Full markdown content of the prompt.
            version_sha: Git SHA used as the Langfuse version label.

        Returns:
            Langfuse version ID string, or None on failure.
        """
        try:
            prompt = self._langfuse_client.create_prompt(
                name=role_id,
                prompt=content,
                labels=[version_sha[:8]],  # Use short SHA as label
                config={"version_sha": version_sha},
            )
            # Langfuse SDK returns an object; extract version ID
            version_id = getattr(prompt, "id", None) or getattr(prompt, "version", None)
            return str(version_id) if version_id is not None else None
        except Exception:
            logger.exception(
                "Langfuse create_prompt() failed for role_id=%s", role_id
            )
            return None
