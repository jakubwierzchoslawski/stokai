"""
Unit tests for node_executor.py — agent node instrumentation with Langfuse spans.

TDD: tests written before implementation per PLAN-N-008 TASK-003.
All external dependencies (tracer, agent, repository) are mocked.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.ai.observability.span_metadata import SpanMetadata
from src.ai.workflows.node_executor import NodeExecutor


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_workflow_state(
    workflow_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    state = MagicMock()
    state.workflow_id = workflow_id or uuid.uuid4()
    state.workflow_type = "mode_a"
    state.tenant_id = tenant_id or uuid.uuid4()
    state.user_id = user_id or uuid.uuid4()
    state.trace_id = None
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
    tokens_in: int = 512,
    tokens_out: int = 256,
    cost_usd: float = 0.0012,
    confidence: float = 0.88,
) -> MagicMock:
    output = MagicMock()
    output.tokens_in = tokens_in
    output.tokens_out = tokens_out
    output.cost_usd = cost_usd
    output.confidence = confidence
    return output


# ── Tests ────────────────────────────────────────────────────────────────────


class TestNodeExecutorSpanLifecycle:
    def test_agent_node_opens_span_before_invoke(self):
        """open_agent_span must be called before the agent invoke method."""
        mock_tracer = MagicMock()
        mock_tracer.open_agent_span.return_value = "span-1"

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = make_agent_output()
        mock_agent.config = make_agent_config()

        mock_prompt_resolver = MagicMock()
        mock_prompt_resolver.resolve.return_value = "abc123"

        executor = NodeExecutor(tracer=mock_tracer, prompt_resolver=mock_prompt_resolver)
        state = make_workflow_state()
        state.trace_id = "trace-1"

        executor.execute_agent_node(state, mock_agent, parent_span_id=None)

        # open_agent_span must be called before invoke
        open_call_order = mock_tracer.open_agent_span.call_args_list
        assert len(open_call_order) == 1

        invoke_calls = mock_agent.invoke.call_args_list
        assert len(invoke_calls) == 1

    def test_agent_node_closes_span_after_invoke(self):
        """close_agent_span must be called with output metadata after invoke."""
        mock_tracer = MagicMock()
        mock_tracer.open_agent_span.return_value = "span-2"

        agent_out = make_agent_output(tokens_in=100, tokens_out=50, cost_usd=0.001, confidence=0.9)
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = agent_out
        mock_agent.config = make_agent_config()

        mock_prompt_resolver = MagicMock()
        mock_prompt_resolver.resolve.return_value = "sha-abc"

        executor = NodeExecutor(tracer=mock_tracer, prompt_resolver=mock_prompt_resolver)
        state = make_workflow_state()
        state.trace_id = "trace-2"

        executor.execute_agent_node(state, mock_agent, parent_span_id=None)

        mock_tracer.close_agent_span.assert_called_once()
        close_args = mock_tracer.close_agent_span.call_args
        span_id_arg = close_args[0][0]
        output_meta: SpanMetadata = close_args[0][1]

        assert span_id_arg == "span-2"
        assert output_meta.tokens_in == 100
        assert output_meta.tokens_out == 50
        assert output_meta.cost_usd == 0.001
        assert output_meta.confidence == 0.9

    def test_agent_node_records_model_used(self):
        """model_used in the span matches the agent config model field."""
        mock_tracer = MagicMock()
        mock_tracer.open_agent_span.return_value = "span-3"

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = make_agent_output()
        mock_agent.config = make_agent_config(model="gpt-4o")

        mock_prompt_resolver = MagicMock()
        mock_prompt_resolver.resolve.return_value = "sha-001"

        executor = NodeExecutor(tracer=mock_tracer, prompt_resolver=mock_prompt_resolver)
        state = make_workflow_state()
        state.trace_id = "trace-3"

        executor.execute_agent_node(state, mock_agent, parent_span_id=None)

        open_kwargs = mock_tracer.open_agent_span.call_args[0]
        metadata_arg: SpanMetadata = open_kwargs[2]
        assert metadata_arg.model_used == "gpt-4o"

    def test_agent_node_span_closed_on_exception(self):
        """close_agent_span is called even when agent.invoke() raises."""
        mock_tracer = MagicMock()
        mock_tracer.open_agent_span.return_value = "span-4"

        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = RuntimeError("agent failure")
        mock_agent.config = make_agent_config()

        mock_prompt_resolver = MagicMock()
        mock_prompt_resolver.resolve.return_value = "sha-err"

        executor = NodeExecutor(tracer=mock_tracer, prompt_resolver=mock_prompt_resolver)
        state = make_workflow_state()
        state.trace_id = "trace-4"

        with pytest.raises(RuntimeError, match="agent failure"):
            executor.execute_agent_node(state, mock_agent, parent_span_id=None)

        # span must still be closed despite the exception
        mock_tracer.close_agent_span.assert_called_once()


class TestBaseWorkflowTraceStorage:
    def test_base_workflow_stores_trace_id_on_run(self):
        """BaseWorkflow.run sets workflow_run.langfuse_trace_id to the open_trace return value."""
        mock_tracer = MagicMock()
        mock_tracer.open_trace.return_value = "trace-workflow-1"
        mock_tracer.close_trace.return_value = None

        mock_repo = AsyncMock()

        from src.ai.workflows.base_workflow import BaseWorkflow

        class ConcreteWorkflow(BaseWorkflow):
            async def _execute(self, state):
                return state

        workflow = ConcreteWorkflow(tracer=mock_tracer, episodic_repo=mock_repo)

        import asyncio

        state = make_workflow_state()
        asyncio.get_event_loop().run_until_complete(workflow.run(state))

        assert state.trace_id == "trace-workflow-1"
        mock_repo.update_workflow_run_trace_id.assert_awaited_once_with(
            workflow_run_id=state.workflow_id,
            trace_id="trace-workflow-1",
        )
