"""Unit tests for LangfuseInvocationLogger.

TDD: tests written before implementation.
REQ-N-008: every agent invocation logs prompt_version (git SHA) to Langfuse span.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.ai.registry.agent_definition import AgentDefinition


def _make_definition(prompt_file: str = "prompts/agents/relevance_analyst.md") -> AgentDefinition:
    return AgentDefinition.model_validate({
        "role_id": "relevance-analyst",
        "persona": "Test persona",
        "system_prompt_file": prompt_file,
        "model": {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-6",
            "temperature": 0.3,
            "max_tokens": 2048,
        },
        "tools": ["get_market_data"],
        "limits": {
            "max_input_tokens": 8000,
            "max_iterations": 3,
            "timeout_seconds": 60,
            "cost_ceiling_usd": 0.10,
        },
        "confidence_threshold": 0.7,
        "output_schema": {},
    })


class TestLoggerCallsLangfuseSpanWithPromptVersion:
    def test_logger_calls_langfuse_span_with_prompt_version(self) -> None:
        """Mock Langfuse client; assert span opened with prompt_version set to non-empty string."""
        from src.ai.observability.langfuse_invocation_logger import LangfuseInvocationLogger

        mock_client = MagicMock()
        mock_span = MagicMock()
        mock_trace = MagicMock()
        mock_trace.span.return_value = mock_span
        mock_client.trace.return_value = mock_trace

        defn = _make_definition()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="abc1234567890abcdef\n", returncode=0
            )
            logger = LangfuseInvocationLogger(
                definition=defn,
                langfuse_client=mock_client,
                workflow_id="wf-test-001",
                tenant_id="tenant-1",
            )
            with logger:
                pass

        # Verify span was created with prompt_version
        mock_client.trace.assert_called_once()
        mock_trace.span.assert_called_once()
        call_kwargs = mock_trace.span.call_args.kwargs
        assert "metadata" in call_kwargs
        assert call_kwargs["metadata"]["prompt_version"] != ""
        assert call_kwargs["metadata"]["prompt_version"] is not None


class TestLoggerRecordsCostAndTokensOnExit:
    def test_logger_records_cost_and_tokens_on_exit(self) -> None:
        """Assert mock span receives cost_usd and token counts on close."""
        from src.ai.observability.langfuse_invocation_logger import LangfuseInvocationLogger

        mock_client = MagicMock()
        mock_span = MagicMock()
        mock_trace = MagicMock()
        mock_trace.span.return_value = mock_span
        mock_client.trace.return_value = mock_trace

        defn = _make_definition()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="abc123\n", returncode=0)
            logger = LangfuseInvocationLogger(
                definition=defn,
                langfuse_client=mock_client,
                workflow_id="wf-test-002",
                tenant_id="tenant-1",
            )
            with logger as ctx:
                ctx.record_usage(
                    cost_usd=0.05,
                    input_tokens=500,
                    output_tokens=200,
                    confidence=0.85,
                )

        mock_span.update.assert_called()
        mock_span.end.assert_called()


class TestLoggerNoOpsWhenLangfuseClientIsNone:
    def test_logger_no_ops_when_langfuse_client_is_none(self) -> None:
        """No exception is raised when Langfuse client is None."""
        from src.ai.observability.langfuse_invocation_logger import LangfuseInvocationLogger

        defn = _make_definition()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="abc123\n", returncode=0)
            logger = LangfuseInvocationLogger(
                definition=defn,
                langfuse_client=None,
                workflow_id="wf-test-003",
                tenant_id="tenant-1",
            )
            with logger as ctx:
                ctx.record_usage(cost_usd=0.01, input_tokens=100, output_tokens=50)


class TestPromptVersionFallsBackToUnknownWhenGitUnavailable:
    def test_prompt_version_falls_back_to_unknown_when_git_unavailable(self) -> None:
        """When subprocess.run raises FileNotFoundError, prompt_version == 'unknown'."""
        from src.ai.observability.langfuse_invocation_logger import LangfuseInvocationLogger

        mock_client = MagicMock()
        mock_span = MagicMock()
        mock_trace = MagicMock()
        mock_trace.span.return_value = mock_span
        mock_client.trace.return_value = mock_trace

        defn = _make_definition()

        with patch(
            "subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            logger = LangfuseInvocationLogger(
                definition=defn,
                langfuse_client=mock_client,
                workflow_id="wf-test-004",
                tenant_id="tenant-1",
            )
            with logger:
                pass

        call_kwargs = mock_trace.span.call_args.kwargs
        assert call_kwargs["metadata"]["prompt_version"] == "unknown"
