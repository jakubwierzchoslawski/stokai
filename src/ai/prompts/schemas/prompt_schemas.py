"""src.ai.prompts.schemas.prompt_schemas — Pydantic models for prompt management.

PLAN-F-014 TASK-002 (AC-002, AC-004).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class PromptLabel(str, Enum):
    """Valid Langfuse label values for prompt versions."""

    production = "production"
    staging = "staging"
    canary = "canary"
    experimental = "experimental"


class PromptFrontmatter(BaseModel):
    """YAML frontmatter parsed from a prompt .md file.

    The ``version`` field is intentionally absent in the source files —
    it is populated after git SHA resolution at publish time.
    """

    version: str | None = Field(
        default=None,
        description="Populated after git SHA resolution; absent in the source file.",
    )
    agent: str = Field(
        description="Role ID (e.g. 'relevance_analyst'). Must match the filename.",
    )
    description: str = Field(
        description="One-line description of the prompt's purpose.",
    )


class PromptFile(BaseModel):
    """Loaded prompt file with parsed frontmatter and git blob SHA.

    Produced by IPromptLoader.load_prompt().
    """

    role_id: str = Field(description="Role identifier derived from the filename.")
    file_path: str = Field(description="Absolute path to the .md file.")
    frontmatter: PromptFrontmatter = Field(description="Parsed YAML frontmatter block.")
    body: str = Field(description="Prompt body text (everything after the frontmatter).")
    sha: str = Field(description="Git blob SHA of the file at HEAD.")


class PromptPublication(BaseModel):
    """Record of a prompt being published (pushed) to Langfuse.

    Written to the prompt_publication DB table and returned by publish_to_langfuse().
    """

    publication_id: UUID = Field(description="Unique identifier for this publication event.")
    role_id: str = Field(description="Prompt role identifier.")
    sha: str = Field(description="Git blob SHA of the published version.")
    langfuse_version: str = Field(
        description="Langfuse version string — equals the git blob SHA."
    )
    published_at: datetime = Field(description="UTC timestamp of the publication.")
    published_by: str = Field(
        description="Actor that triggered the publish: 'ci' | 'cli' | 'admin'.",
    )
