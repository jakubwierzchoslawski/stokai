"""
Unit tests for node_executor.py — PostgreSQL dual-write after Langfuse span close.

TDD: tests written before implementation per PLAN-N-008 TASK-005.

Dual-write semantics (per PLAN-F-015 invariant):
- Langfuse span close is best-effort: Langfuse outage must NOT abort the workflow.
- EpisodicRepository write is authoritative: failure propagates and fails the workflow.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.ai.workflows.node_executor import NodeExecutor


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_workflow_state(**kwargs) -> MagicMock:
    state = MagicMock()
    state.workflow_id = kwargs.get("workflow_id", uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"))
    state.workflow_type = "mode_a"
    state.tenant_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
    state.user_id = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
    state.trace_id = "trace-db-001"
    state.cost_usd = 0.0
    return state


def make_agent_config(
    agent_role_id: str = "risk_analyst",
    model: str = "claude-3-5-sonnet-20241022",
    prompt_path: str = "prompts/risk_analyst.yaml",
) -> MagicMock:
    config = MagicMock()
    config.agent_role_id = agent_role_id
    config.model = model
    config.prompt_path = prompt_path
    return config


def make_agent_output(
    tokens_in: int = 256,
    tokens_out: int = 128,
    cost_usd: float = 0.0008,
    confidence: float = 0.91,
) -> MagicMock:
    out = MagicMock()
    out.tokens_in = tokens_in
    out.tokens_out = tokens_out
    out.cost_usd = cost_usd
    out.confidence = confidence
    return out


def make_tracer(span_id: str = "span-db-001") -> MagicMock:
    tracer = MagicMock()
    tracer.open_agent_span.return_value = span_id
    tracer.close_agent_span.return_value = None
    return tracer


def make_prompt_resolver(sha: str = "deadbeef") -> MagicMock:
    resolver = MagicMock()
    resolver.resolve.return_value = sha
    return resolver


# ── Tests ────────────────────────────────────────────────────────────────────


class TestAgentInvocationRowWrite:
    def test_agent_invocation_row_written_after_span_close(self):
        """EpisodicRepository.append_agent_invocation is called once per agent execution."""
        mock_tracer = make_tracer(span_id="span-write-1")
        mock_repo = MagicMock()
        mock_repo.append_agent_invocation = AsyncMock()

        agent_output = make_agent_output(cost_usd=0.0042)
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = agent_output
        mock_agent.config = make_agent_config(
            agent_role_id="portfolio_scorer", prompt_path="prompts/scorer.yaml"
        )

        resolver = make_prompt_resolver(sha="sha-abc")

        executor = NodeExecutor(
            tracer=mock_tracer, prompt_resolver=resolver, episodic_repo=mock_repo
        )
        state = make_workflow_state()

        import asyncio

        asyncio.get_event_loop().run_until_complete(
            executor.execute_agent_node_async(state, mock_agent, parent_span_id=None)
        )

        mock_repo.append_agent_invocation.assert_awaited_once()
        call_kwargs = mock_repo.append_agent_invocation.call_args[1]
        assert call_kwargs["workflow_run_id"] == state.workflow_id
        assert call_kwargs["agent_role"] == "portfolio_scorer"
        assert call_kwargs["prompt_version"] == "sha-abc"
        assert call_kwargs["cost_usd"] == pytest.approx(0.0042)

    def test_agent_invocation_cost_matches_span_cost(self):
        """cost_usd on the DB row equals the cost passed to close_agent_span."""
        mock_tracer = make_tracer(span_id="span-cost-1")
        mock_repo = MagicMock()
        mock_repo.append_agent_invocation = AsyncMock()

        expected_cost = 0.0099
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = make_agent_output(cost_usd=expected_cost)
        mock_agent.config = make_agent_config()

        executor = NodeExecutor(
            tracer=mock_tracer,
            prompt_resolver=make_prompt_resolver(),
            episodic_repo=mock_repo,
        )
        state = make_workflow_state()

        import asyncio

        asyncio.get_event_loop().run_until_complete(
            executor.execute_agent_node_async(state, mock_agent, parent_span_id=None)
        )

        # Extract close_agent_span output metadata
        close_args = mock_tracer.close_agent_span.call_args[0]
        output_metadata = close_args[1]

        # Extract DB write cost
        db_cost = mock_repo.append_agent_invocation.call_args[1]["cost_usd"]

        assert db_cost == pytest.approx(output_metadata.cost_usd)
        assert db_cost == pytest.approx(expected_cost)


class TestToolCallRowWrite:
    def test_tool_call_row_written_after_tool_span_close(self):
        """EpisodicRepository.append_tool_call is called after close_tool_span."""
        mock_tracer = MagicMock()
        mock_tracer.open_tool_span.return_value = "tool-span-1"
        mock_tracer.close_tool_span.return_value = None

        mock_repo = MagicMock()
        mock_repo.append_tool_call = AsyncMock()

        executor = NodeExecutor(
            tracer=mock_tracer,
            prompt_resolver=make_prompt_resolver(),
            episodic_repo=mock_repo,
        )
        state = make_workflow_state()

        import asyncio

        asyncio.get_event_loop().run_until_complete(
            executor.execute_tool_call_async(
                state=state,
                invocation_id=uuid.UUID("00000000-0000-0000-0000-000000000099"),
                tool_name="market_data_tool",
                parent_span_id="span-parent-1",
                args_hash="hash123",
                cached=False,
                result_rows=5,
                latency_ms=300,
                error_type=None,
            )
        )

        mock_repo.append_tool_call.assert_awaited_once()
        call_kwargs = mock_repo.append_tool_call.call_args[1]
        assert call_kwargs["tool_name"] == "market_data_tool"
        assert call_kwargs["invocation_id"] == uuid.UUID(
            "00000000-0000-0000-0000-000000000099"
        )


class TestLangfuseBestEffort:
    def test_db_write_failure_does_not_suppress_span(self):
        """When EpisodicRepository.append_agent_invocation raises, the span still closes.

        Note: per PLAN-N-008 TASK-005, the episodic write IS authoritative.
        This test verifies that if the DB write fails the exception propagates
        (workflow fails), but the Langfuse span was already closed before the DB
        write attempt, so it is not suppressed.
        """
        mock_tracer = make_tracer(span_id="span-fail-1")
        mock_repo = MagicMock()
        mock_repo.append_agent_invocation = AsyncMock(side_effect=RuntimeError("DB down"))

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = make_agent_output()
        mock_agent.config = make_agent_config()

        executor = NodeExecutor(
            tracer=mock_tracer,
            prompt_resolver=make_prompt_resolver(),
            episodic_repo=mock_repo,
        )
        state = make_workflow_state()

        import asyncio

        with pytest.raises(RuntimeError, match="DB down"):
            asyncio.get_event_loop().run_until_complete(
                executor.execute_agent_node_async(state, mock_agent, parent_span_id=None)
            )

        # Langfuse span must have been closed before the DB write was attempted
        mock_tracer.close_agent_span.assert_called_once()
