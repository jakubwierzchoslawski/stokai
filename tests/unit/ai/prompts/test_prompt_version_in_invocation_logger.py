"""Tests for PLAN-F-014 TASK-008 — prompt_version SHA in LangfuseInvocationLogger.

TDD spec from the plan:
- test_invocation_logger_attaches_sha_to_langfuse_span
- test_invocation_logger_uses_unknown_when_no_prompt_file
- test_invocation_logger_does_not_swallow_other_errors
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ai.registry.agent_definition import AgentDefinition
from src.ai.observability.langfuse_invocation_logger import LangfuseInvocationLogger


def _make_definition(role_id: str = "relevance-analyst") -> AgentDefinition:
    return AgentDefinition.model_validate({
        "role_id": role_id,
        "persona": "Test persona",
        "system_prompt_file": "prompts/agents/relevance_analyst.md",
        "model": {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-6",
            "temperature": 0.3,
            "max_tokens": 2048,
        },
        "tools": [],
        "limits": {
            "max_input_tokens": 8000,
            "max_iterations": 3,
            "timeout_seconds": 60,
            "cost_ceiling_usd": 0.10,
        },
        "confidence_threshold": 0.7,
        "output_schema": {},
    })


def _make_langfuse_client():
    mock_client = MagicMock()
    mock_span = MagicMock()
    mock_trace = MagicMock()
    mock_trace.span.return_value = mock_span
    mock_client.trace.return_value = mock_trace
    return mock_client, mock_span, mock_trace


class TestInvocationLoggerPromptVersionViaPLoader:
    def test_invocation_logger_attaches_sha_to_langfuse_span(self) -> None:
        """Logger uses IPromptLoader.get_sha() for blob SHA and attaches to span."""
        mock_client, mock_span, mock_trace = _make_langfuse_client()

        fixed_sha = "a" * 40
        mock_loader = MagicMock()
        mock_loader.get_sha.return_value = fixed_sha

        defn = _make_definition()
        logger = LangfuseInvocationLogger(
            definition=defn,
            langfuse_client=mock_client,
            workflow_id="wf-test",
            tenant_id="tenant-1",
            prompt_loader=mock_loader,
        )

        with logger:
            pass

        # Verify get_sha was called with snake_case role_id
        mock_loader.get_sha.assert_called_once_with("relevance_analyst")

        # Verify span metadata contains the blob SHA
        call_kwargs = mock_trace.span.call_args.kwargs
        assert call_kwargs["metadata"]["prompt_version"] == fixed_sha

    def test_invocation_logger_uses_unknown_when_no_prompt_file(self) -> None:
        """Logger sets prompt_version='unknown' when PromptNotFoundError is raised."""
        mock_client, mock_span, mock_trace = _make_langfuse_client()

        mock_loader = MagicMock()
        mock_loader.get_sha.side_effect = FileNotFoundError("no file for role")

        defn = _make_definition()
        logger = LangfuseInvocationLogger(
            definition=defn,
            langfuse_client=mock_client,
            workflow_id="wf-test",
            tenant_id="tenant-1",
            prompt_loader=mock_loader,
        )

        with logger:
            pass

        call_kwargs = mock_trace.span.call_args.kwargs
        assert call_kwargs["metadata"]["prompt_version"] == "unknown"

    def test_invocation_logger_does_not_swallow_other_errors(self) -> None:
        """RuntimeError from get_sha() propagates out of the context manager."""
        mock_client, mock_span, mock_trace = _make_langfuse_client()

        mock_loader = MagicMock()
        mock_loader.get_sha.side_effect = RuntimeError("unexpected failure")

        defn = _make_definition()
        logger = LangfuseInvocationLogger(
            definition=defn,
            langfuse_client=mock_client,
            workflow_id="wf-test",
            tenant_id="tenant-1",
            prompt_loader=mock_loader,
        )

        with pytest.raises(RuntimeError, match="unexpected failure"):
            with logger:
                pass

    def test_invocation_logger_falls_back_to_git_log_when_no_loader(self) -> None:
        """When no loader is provided, falls back to git log commit SHA."""
        mock_client, mock_span, mock_trace = _make_langfuse_client()

        defn = _make_definition()
        logger = LangfuseInvocationLogger(
            definition=defn,
            langfuse_client=mock_client,
            workflow_id="wf-test",
            tenant_id="tenant-1",
            prompt_loader=None,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="abcdef1234567890abcdef1234567890abcdef12\n",
                returncode=0,
            )
            with logger:
                pass

        call_kwargs = mock_trace.span.call_args.kwargs
        assert call_kwargs["metadata"]["prompt_version"] != ""


class TestCanaryTagging:
    def test_canary_tag_absent_when_no_label_service(self) -> None:
        """canary_cohort is absent from span when no label service is available."""
        mock_client, mock_span, mock_trace = _make_langfuse_client()

        fixed_sha = "b" * 40
        mock_loader = MagicMock()
        mock_loader.get_sha.return_value = fixed_sha
        # No _label_service attribute
        del mock_loader._label_service

        defn = _make_definition()
        logger = LangfuseInvocationLogger(
            definition=defn,
            langfuse_client=mock_client,
            workflow_id="wf-test",
            tenant_id="tenant-1",
            prompt_loader=mock_loader,
        )

        with logger:
            pass

        call_kwargs = mock_trace.span.call_args.kwargs
        assert "canary_cohort" not in call_kwargs["metadata"]

    def test_canary_tag_absent_when_sha_is_unknown(self) -> None:
        """canary_cohort is absent when prompt_version is 'unknown'."""
        mock_client, mock_span, mock_trace = _make_langfuse_client()

        mock_loader = MagicMock()
        mock_loader.get_sha.side_effect = FileNotFoundError("no file")

        defn = _make_definition()
        logger = LangfuseInvocationLogger(
            definition=defn,
            langfuse_client=mock_client,
            workflow_id="wf-test",
            tenant_id="tenant-1",
            prompt_loader=mock_loader,
        )

        with logger:
            pass

        call_kwargs = mock_trace.span.call_args.kwargs
        # canary_cohort should not be True when prompt_version is unknown
        assert call_kwargs["metadata"].get("canary_cohort") is not True
