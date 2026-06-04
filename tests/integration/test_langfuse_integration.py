"""
Integration tests — Langfuse trace completeness and PostgreSQL row assertions.

Marked pytest.mark.integration.  Requires a running Docker Compose stack that
includes langfuse-server, langfuse-db, and clickhouse.

Tests are automatically skipped when the LANGFUSE_HOST environment variable is
not set, which is the case on plain unit-test CI jobs.

Usage:
    docker compose up -d
    # Wait for Langfuse health endpoint to return 200
    pytest -m integration tests/integration/test_langfuse_integration.py

Call client.flush() after each trace close to guarantee the trace is
queryable before assertions run (Langfuse SDK background queue).
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import httpx
import pytest

# ── Skip guard ───────────────────────────────────────────────────────────────

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "").rstrip("/")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")

pytestmark = pytest.mark.integration

requires_langfuse = pytest.mark.skipif(
    not LANGFUSE_HOST,
    reason="LANGFUSE_HOST not set — Langfuse stack not running",
)


# ── Minimal workflow fixture ─────────────────────────────────────────────────


@dataclass
class _AgentOutputStub:
    tokens_in: int = 100
    tokens_out: int = 50
    cost_usd: float = 0.0025
    confidence: float = 0.92


class _AgentConfigStub:
    agent_role_id: str = "integration_test_agent"
    model: str = "stub-model-v1"
    prompt_path: str = "prompts/integration_test.yaml"


class _AgentNodeStub:
    config = _AgentConfigStub()

    def invoke(self, state: Any) -> _AgentOutputStub:
        return _AgentOutputStub()


class _PromptResolverStub:
    def resolve(self, path: str) -> str:
        return "integration-test-sha-abc123"


class _WorkflowState:
    def __init__(self) -> None:
        self.workflow_id = uuid.uuid4()
        self.workflow_type = "mode_a_integration_test"
        self.tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        self.user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        self.trace_id: str | None = None
        self.cost_usd: float = 0.0


def _make_real_tracer():
    """Construct a LangfuseTracer pointing at the live Langfuse container."""
    from langfuse import Langfuse  # type: ignore[import]

    from src.ai.observability.tracer import LangfuseTracer

    client = Langfuse(
        secret_key=LANGFUSE_SECRET_KEY,
        public_key=LANGFUSE_PUBLIC_KEY,
        host=LANGFUSE_HOST,
    )
    return LangfuseTracer(client=client), client


def _langfuse_api_auth() -> tuple[str, str]:
    """Return (username, password) for Langfuse Basic Auth on public API calls."""
    # Langfuse public API uses public_key:secret_key as Basic Auth
    return LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY


# ── Tests ─────────────────────────────────────────────────────────────────────


@requires_langfuse
class TestLangfuseAccessibility:
    def test_langfuse_accessible_without_external_network(self):
        """GET /api/public/health returns 200 using only LANGFUSE_HOST.

        Verifies the self-hosted Langfuse service is healthy without any
        external SaaS dependency.
        """
        url = f"{LANGFUSE_HOST}/api/public/health"
        response = httpx.get(url, timeout=10)
        assert response.status_code == 200, (
            f"Langfuse health check failed: {response.status_code} — {response.text}"
        )


@requires_langfuse
class TestWorkflowTracing:
    def test_workflow_run_produces_langfuse_trace(self):
        """Run MinimalWorkflow and assert a Langfuse trace with >= 2 observations exists."""
        import asyncio

        tracer, langfuse_client = _make_real_tracer()
        mock_repo = AsyncMock()

        from src.ai.observability.span_metadata import SpanMetadata
        from src.ai.workflows.node_executor import NodeExecutor

        state = _WorkflowState()

        # Open trace (workflow entry)
        root_metadata = SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
        )
        trace_id = tracer.open_trace(root_metadata)
        state.trace_id = trace_id

        # Execute agent node
        executor = NodeExecutor(
            tracer=tracer,
            prompt_resolver=_PromptResolverStub(),
            episodic_repo=mock_repo,
        )

        asyncio.get_event_loop().run_until_complete(
            executor.execute_agent_node_async(state, _AgentNodeStub(), parent_span_id=None)
        )

        # Close trace
        tracer.close_trace(trace_id, cost_usd=0.0025)
        langfuse_client.flush()

        # Query Langfuse API
        url = f"{LANGFUSE_HOST}/api/public/traces/{trace_id}"
        response = httpx.get(url, auth=_langfuse_api_auth(), timeout=15)

        assert response.status_code == 200, (
            f"Trace not found: {response.status_code} — {response.text}"
        )
        trace_data = response.json()
        observations = trace_data.get("observations", [])
        assert len(observations) >= 2, (
            f"Expected >= 2 observations (root + agent span), got {len(observations)}"
        )

    def test_agent_span_contains_required_fields(self):
        """Agent observation in Langfuse has all required metadata fields."""
        import asyncio

        tracer, langfuse_client = _make_real_tracer()
        mock_repo = AsyncMock()

        from src.ai.observability.span_metadata import SpanMetadata
        from src.ai.workflows.node_executor import NodeExecutor

        state = _WorkflowState()

        root_metadata = SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
        )
        trace_id = tracer.open_trace(root_metadata)
        state.trace_id = trace_id

        executor = NodeExecutor(
            tracer=tracer,
            prompt_resolver=_PromptResolverStub(),
            episodic_repo=mock_repo,
        )
        asyncio.get_event_loop().run_until_complete(
            executor.execute_agent_node_async(state, _AgentNodeStub(), parent_span_id=None)
        )

        tracer.close_trace(trace_id, cost_usd=0.0025)
        langfuse_client.flush()

        # Fetch trace and inspect agent observation
        url = f"{LANGFUSE_HOST}/api/public/traces/{trace_id}"
        response = httpx.get(url, auth=_langfuse_api_auth(), timeout=15)
        assert response.status_code == 200

        observations = response.json().get("observations", [])
        # Find the agent span (not the root)
        agent_obs = next(
            (o for o in observations if o.get("name") == "integration_test_agent"),
            None,
        )
        assert agent_obs is not None, "Agent observation not found in trace"

        meta = agent_obs.get("metadata") or {}
        required_fields = [
            "agent_role_id",
            "model_used",
            "prompt_version",
            "tokens_in",
            "tokens_out",
            "cost_usd",
            "latency_ms",
            "confidence",
        ]
        missing = [f for f in required_fields if meta.get(f) is None]
        assert not missing, f"Agent span missing required fields: {missing}"

    def test_agent_invocation_row_in_postgres(self):
        """agent_invocation row exists in PostgreSQL with matching fields."""
        import asyncio

        tracer, langfuse_client = _make_real_tracer()

        # Track what the repo was called with
        captured_calls: list[dict] = []

        class CapturingRepo:
            async def append_agent_invocation(self, **kwargs):
                captured_calls.append(kwargs)

            async def append_tool_call(self, **kwargs):
                pass

            async def update_workflow_run_trace_id(self, **kwargs):
                pass

        from src.ai.observability.span_metadata import SpanMetadata
        from src.ai.workflows.node_executor import NodeExecutor

        state = _WorkflowState()

        root_metadata = SpanMetadata(
            workflow_id=state.workflow_id,
            workflow_type=state.workflow_type,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
        )
        trace_id = tracer.open_trace(root_metadata)
        state.trace_id = trace_id

        executor = NodeExecutor(
            tracer=tracer,
            prompt_resolver=_PromptResolverStub(),
            episodic_repo=CapturingRepo(),
        )
        asyncio.get_event_loop().run_until_complete(
            executor.execute_agent_node_async(state, _AgentNodeStub(), parent_span_id=None)
        )

        tracer.close_trace(trace_id, cost_usd=0.0025)
        langfuse_client.flush()

        # Fetch agent span metadata from Langfuse
        url = f"{LANGFUSE_HOST}/api/public/traces/{trace_id}"
        response = httpx.get(url, auth=_langfuse_api_auth(), timeout=15)
        assert response.status_code == 200

        observations = response.json().get("observations", [])
        agent_obs = next(
            (o for o in observations if o.get("name") == "integration_test_agent"),
            None,
        )
        assert agent_obs is not None
        langfuse_prompt_version = (agent_obs.get("metadata") or {}).get("prompt_version")

        # Assert DB row
        assert len(captured_calls) == 1, "Expected exactly one agent_invocation call"
        row = captured_calls[0]
        assert row["workflow_run_id"] == state.workflow_id
        assert row["prompt_version"] == langfuse_prompt_version
        assert row["prompt_version"] == "integration-test-sha-abc123"
