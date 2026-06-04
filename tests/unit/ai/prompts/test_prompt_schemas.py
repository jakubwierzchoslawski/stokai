"""Tests for Pydantic prompt schemas — TDD for PLAN-F-014 TASK-002."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.ai.prompts.schemas.prompt_schemas import (
    PromptFile,
    PromptFrontmatter,
    PromptLabel,
    PromptPublication,
)
from src.ai.prompts.schemas.rollback_schemas import RollbackRequest, RollbackResult


# ---------------------------------------------------------------------------
# PromptFrontmatter
# ---------------------------------------------------------------------------


class TestPromptFrontmatter:
    def test_parses_valid_frontmatter(self) -> None:
        fm = PromptFrontmatter(agent="relevance_analyst", description="Assesses event relevance.")
        assert fm.agent == "relevance_analyst"
        assert fm.description == "Assesses event relevance."
        assert fm.version is None  # blank in source files

    def test_version_populated_after_sha_resolution(self) -> None:
        sha = "a" * 40
        fm = PromptFrontmatter(version=sha, agent="relevance_analyst", description="...")
        assert fm.version == sha

    def test_agent_field_required(self) -> None:
        with pytest.raises(Exception):
            PromptFrontmatter(description="Missing agent field.")


# ---------------------------------------------------------------------------
# PromptFile
# ---------------------------------------------------------------------------


class TestPromptFile:
    def test_prompt_file_holds_all_fields(self) -> None:
        sha = "b" * 40
        fm = PromptFrontmatter(agent="anomaly_detector", description="Detects anomalies.")
        pf = PromptFile(
            role_id="anomaly_detector",
            file_path="/prompts/agents/anomaly_detector.md",
            frontmatter=fm,
            body="You are an anomaly detector.",
            sha=sha,
        )
        assert pf.role_id == "anomaly_detector"
        assert pf.sha == sha
        assert pf.body == "You are an anomaly detector."

    def test_sha_is_40_chars(self) -> None:
        sha = "c" * 40
        pf = PromptFile(
            role_id="exposure_analyst",
            file_path="/prompts/agents/exposure_analyst.md",
            frontmatter=PromptFrontmatter(agent="exposure_analyst", description="..."),
            body="body",
            sha=sha,
        )
        assert len(pf.sha) == 40


# ---------------------------------------------------------------------------
# PromptLabel
# ---------------------------------------------------------------------------


class TestPromptLabel:
    def test_all_four_labels_exist(self) -> None:
        assert PromptLabel.production == "production"
        assert PromptLabel.staging == "staging"
        assert PromptLabel.canary == "canary"
        assert PromptLabel.experimental == "experimental"

    def test_label_from_string(self) -> None:
        assert PromptLabel("production") is PromptLabel.production


# ---------------------------------------------------------------------------
# PromptPublication
# ---------------------------------------------------------------------------


class TestPromptPublication:
    def test_prompt_publication_holds_all_fields(self) -> None:
        pub = PromptPublication(
            publication_id=uuid4(),
            role_id="narrative_writer",
            sha="d" * 40,
            langfuse_version="d" * 40,
            published_at=datetime.now(tz=timezone.utc),
            published_by="ci",
        )
        assert pub.role_id == "narrative_writer"
        assert pub.published_by == "ci"


# ---------------------------------------------------------------------------
# RollbackRequest / RollbackResult
# ---------------------------------------------------------------------------


class TestRollbackSchemas:
    def test_rollback_request_valid(self) -> None:
        req = RollbackRequest(role_id="exposure_analyst", to_version="e" * 40)
        assert req.to_version == "e" * 40
        assert req.published_by == "cli"  # default

    def test_rollback_request_sha_must_be_40_chars(self) -> None:
        with pytest.raises(Exception):
            RollbackRequest(role_id="exposure_analyst", to_version="tooshort")

    def test_rollback_result_holds_all_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        result = RollbackResult(
            role_id="exposure_analyst",
            previous_version="f" * 40,
            rolled_back_to="g" * 40,
            effective_at=now,
        )
        assert result.previous_version == "f" * 40
        assert result.rolled_back_to == "g" * 40
        assert result.effective_at == now
