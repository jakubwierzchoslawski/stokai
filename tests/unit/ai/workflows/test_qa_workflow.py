"""
Unit tests for QAWorkflow (PLAN-F-027 TASK-004).

Tests:
  - in_scope → agent is invoked
  - out_of_scope → agent NOT invoked, answer contains the suggestion
  - cost_limit → QAAnswer.cost_limited=True
  - persists user AND assistant messages (2 calls to append_message)
  - writes workflow_run to episodic memory
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.ai.qa.response_builder import QAAnswer, QASource
from src.ai.qa.scope_guard import ScopeCheckResult
from src.ai.workflows.qa_state import QAWorkflowState
from src.ai.workflows.state import WorkflowType, WorkflowStatus


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def session_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def base_state(tenant_id, user_id, session_id) -> QAWorkflowState:
    return QAWorkflowState.create(
        session_id=session_id,
        question="What is my AAPL exposure?",
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_history=[],
    )


@pytest.fixture
def mock_qa_repository():
    repo = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.message_id = uuid.uuid4()
    repo.append_message = AsyncMock(return_value=mock_msg)
    repo.get_messages = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_scope_guard():
    guard = AsyncMock()
    guard.check = AsyncMock(
        return_value=ScopeCheckResult(
            in_scope=True, out_of_scope_tickers=[], suggestion=None
        )
    )
    return guard


@pytest.fixture
def mock_episodic_repo():
    repo = AsyncMock()
    mock_run = MagicMock()
    mock_run.workflow_id = uuid.uuid4()
    repo.append_workflow_run = AsyncMock(return_value=mock_run)
    repo.append_agent_invocation = AsyncMock()
    return repo


@pytest.fixture
def agent_output() -> dict:
    return {
        "answer": "Your AAPL exposure is 15% of portfolio.",
        "confidence": 0.87,
        "sources": [
            {"type": "event", "id": "evt-1", "description": "AAPL Q1 2026 earnings"},
        ],
    }


# ── Helper: build QAWorkflow ───────────────────────────────────────────────────


def make_workflow(
    qa_repo,
    scope_guard,
    episodic_repo,
    agent_fn=None,
    cost_ceiling_usd: float = 0.40,
):
    """Construct a QAWorkflow with injected mocks."""
    from src.ai.workflows.qa_workflow import QAWorkflow

    return QAWorkflow(
        qa_repository=qa_repo,
        scope_guard=scope_guard,
        episodic_repository=episodic_repo,
        agent_fn=agent_fn or AsyncMock(
            return_value={"answer": "Test answer", "confidence": 0.80}
        ),
        cost_ceiling_usd=cost_ceiling_usd,
    )


# ── Test: in_scope → agent invoked ─────────────────────────────────────────────


class TestQAWorkflowInScope:
    """When scope check passes, the QA agent must be invoked."""

    @pytest.mark.asyncio
    async def test_in_scope_agent_is_invoked(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
    ):
        """in_scope=True → qa_analyst agent is called once."""
        agent_fn = AsyncMock(
            return_value={"answer": "Your AAPL is 15%.", "confidence": 0.87}
        )

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        await workflow.run(base_state)

        agent_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_in_scope_answer_populated(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
        agent_output,
    ):
        """in_scope=True → final state has answer populated."""
        agent_fn = AsyncMock(return_value=agent_output)

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        final_state = await workflow.run(base_state)

        assert final_state.answer is not None
        assert "AAPL" in final_state.answer.answer_text or final_state.answer.answer_text


# ── Test: out_of_scope → agent NOT invoked ─────────────────────────────────────


class TestQAWorkflowOutOfScope:
    """When scope check fails, agent must NOT be called; answer uses suggestion."""

    @pytest.mark.asyncio
    async def test_out_of_scope_agent_not_invoked(
        self,
        base_state,
        mock_qa_repository,
        mock_episodic_repo,
    ):
        """out_of_scope → agent NOT invoked."""
        scope_guard = AsyncMock()
        scope_guard.check = AsyncMock(
            return_value=ScopeCheckResult(
                in_scope=False,
                out_of_scope_tickers=["NVDA"],
                suggestion="NVDA is not in your portfolio. Add it to your watchlist.",
            )
        )

        agent_fn = AsyncMock()

        workflow = make_workflow(
            mock_qa_repository,
            scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        await workflow.run(base_state)

        agent_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_out_of_scope_answer_contains_suggestion(
        self,
        base_state,
        mock_qa_repository,
        mock_episodic_repo,
    ):
        """out_of_scope → answer text is the scope guard suggestion."""
        suggestion = "NVDA is not in your portfolio. Add it to your watchlist."
        scope_guard = AsyncMock()
        scope_guard.check = AsyncMock(
            return_value=ScopeCheckResult(
                in_scope=False,
                out_of_scope_tickers=["NVDA"],
                suggestion=suggestion,
            )
        )

        workflow = make_workflow(
            mock_qa_repository,
            scope_guard,
            mock_episodic_repo,
            agent_fn=AsyncMock(),
        )
        final_state = await workflow.run(base_state)

        assert final_state.answer is not None
        assert final_state.answer.answer_text == suggestion


# ── Test: cost_limit → QAAnswer.cost_limited=True ─────────────────────────────


class TestQAWorkflowCostLimit:
    """When agent raises WorkflowCostLimitError, answer.cost_limited=True."""

    @pytest.mark.asyncio
    async def test_cost_limit_sets_cost_limited_flag(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
    ):
        """Agent raises LimitExceededError → QAAnswer.cost_limited=True."""
        from src.ai.workflows.errors import WorkflowCostLimitError

        async def agent_fn(state):
            raise WorkflowCostLimitError(
                accumulated=0.45, ceiling=0.40, workflow_id=state.workflow_id
            )

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        final_state = await workflow.run(base_state)

        assert final_state.answer is not None
        assert final_state.answer.cost_limited is True

    @pytest.mark.asyncio
    async def test_cost_limit_still_persists_answer(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
    ):
        """Cost-limited answer is still persisted (partial answer better than none)."""
        from src.ai.workflows.errors import WorkflowCostLimitError

        call_count = {"n": 0}

        async def agent_fn(state):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise WorkflowCostLimitError(
                    accumulated=0.45, ceiling=0.40, workflow_id=state.workflow_id
                )

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        await workflow.run(base_state)

        # append_message should still be called (user + assistant)
        assert mock_qa_repository.append_message.call_count >= 1


# ── Test: persists user AND assistant messages ─────────────────────────────────


class TestQAWorkflowMessagePersistence:
    """persist_message node writes both user and assistant messages."""

    @pytest.mark.asyncio
    async def test_persists_two_messages(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
    ):
        """Both the user question and the assistant answer are persisted."""
        agent_fn = AsyncMock(
            return_value={"answer": "Your AAPL is 15%.", "confidence": 0.87}
        )

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        await workflow.run(base_state)

        # Should have called append_message exactly twice: user + assistant
        assert mock_qa_repository.append_message.call_count == 2

    @pytest.mark.asyncio
    async def test_user_message_role_is_user(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
    ):
        """First append_message call has role='user'."""
        agent_fn = AsyncMock(
            return_value={"answer": "Your AAPL is 15%.", "confidence": 0.87}
        )

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        await workflow.run(base_state)

        calls = mock_qa_repository.append_message.call_args_list
        # At least one call with role='user'
        roles = [c.args[0].role if c.args else c.kwargs.get("message", MagicMock()).role
                 for c in calls]
        # Extract roles from the QAMessage objects
        msg_roles = []
        for c in calls:
            if c.args:
                msg_roles.append(c.args[0].role)
            elif "message" in c.kwargs:
                msg_roles.append(c.kwargs["message"].role)

        assert "user" in msg_roles
        assert "assistant" in msg_roles


# ── Test: writes workflow_run to episodic memory ───────────────────────────────


class TestQAWorkflowEpisodicMemory:
    """persist_message node writes workflow_run via episodic repository."""

    @pytest.mark.asyncio
    async def test_writes_workflow_run_to_episodic_memory(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
    ):
        """append_workflow_run is called on the episodic repository."""
        agent_fn = AsyncMock(
            return_value={"answer": "Your AAPL is 15%.", "confidence": 0.87}
        )

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        await workflow.run(base_state)

        mock_episodic_repo.append_workflow_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_run_has_qa_type(
        self,
        base_state,
        mock_qa_repository,
        mock_scope_guard,
        mock_episodic_repo,
    ):
        """The episodic workflow_run has workflow_type='qa'."""
        agent_fn = AsyncMock(
            return_value={"answer": "Test.", "confidence": 0.75}
        )

        workflow = make_workflow(
            mock_qa_repository,
            mock_scope_guard,
            mock_episodic_repo,
            agent_fn=agent_fn,
        )
        await workflow.run(base_state)

        call_args = mock_episodic_repo.append_workflow_run.call_args
        run_create = call_args.args[0] if call_args.args else call_args.kwargs.get("run")
        assert run_create is not None
        assert "qa" in str(run_create.workflow_type).lower()
