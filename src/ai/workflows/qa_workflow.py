"""
ai.workflows.qa_workflow — QAWorkflow: LangGraph-style Q&A session workflow.

PLAN-F-027 TASK-004

Node sequence:
  1. load_session_context  — load prior conversation history from QARepository
  2. check_scope           — QAScopeGuard: validates question is portfolio-scoped
  3. run_qa_analyst        — invoke the qa-analyst agent (async callable)
  4. build_response        — QAResponseBuilder: build QAAnswer from agent output
  5. persist_message       — save user+assistant messages + write episodic memory

Routing:
  check_scope: if in_scope=False → write suggestion as answer, skip agent,
               route directly to persist_message.

Cost ceiling:
  run_qa_analyst catches WorkflowCostLimitError → sets cost_limited=True,
  continues to build_response with whatever partial output is available.

Episodic memory:
  persist_message writes a workflow_run row via IEpisodicRepository.
  workflow_type="qa"; final_state=QAWorkflowState snapshot.
  Also writes an agent_invocation row for qa_analyst.

Note: QAWorkflow runs INLINE (not as a Celery task) to support SSE streaming.
      This is an accepted MVP scaling limitation documented here.
      TODO(scaling): migrate to Celery when session volume demands it.

WorkflowStructureValidator is invoked with skip_tail_invariant=True because
Q&A is interactive and does not require the evaluate_quality+narrative_writer tail.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable
from uuid import UUID, uuid4

from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocationCreate,
    WorkflowRunCreate,
)
from src.ai.qa.response_builder import QAAnswer, QAResponseBuilder
from src.ai.qa.scope_guard import QAScopeGuard, ScopeCheckResult
from src.ai.workflows.errors import WorkflowCostLimitError
from src.ai.workflows.qa_state import QAWorkflowState
from src.storage.repositories.qa_repository import IQARepository, QAMessage

logger = logging.getLogger(__name__)

# Agent callable type: (state) -> dict  (the raw agent output)
AgentFn = Callable[[QAWorkflowState], Awaitable[dict[str, Any]]]


class QAWorkflow:
    """
    Sequential Q&A workflow with inline SSE-compatible execution.

    All nodes are implemented as async methods on this class. There is no
    external LangGraph StateGraph dependency — the node sequence is executed
    directly to avoid blocking and to support SSE streaming.

    Parameters
    ----------
    qa_repository:
        IQARepository implementation for session/message persistence.
    scope_guard:
        QAScopeGuard instance for portfolio scope checking.
    episodic_repository:
        IEpisodicRepository for writing workflow_run and agent_invocation rows.
    agent_fn:
        Async callable that invokes the qa-analyst agent and returns a dict.
    cost_ceiling_usd:
        Per-session cost ceiling. Default: $0.40 per plan spec.
    """

    def __init__(
        self,
        qa_repository: IQARepository,
        scope_guard: QAScopeGuard,
        episodic_repository: Any,  # IEpisodicRepository
        agent_fn: AgentFn,
        cost_ceiling_usd: float = 0.40,
    ) -> None:
        self._qa_repo = qa_repository
        self._scope_guard = scope_guard
        self._episodic_repo = episodic_repository
        self._agent_fn = agent_fn
        self._cost_ceiling_usd = cost_ceiling_usd
        self._response_builder = QAResponseBuilder()

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, state: QAWorkflowState) -> QAWorkflowState:
        """Execute the full Q&A workflow node sequence.

        Returns the final QAWorkflowState with answer populated.

        Node sequence:
          load_session_context → check_scope → [run_qa_analyst → build_response]
          OR [write_out_of_scope_answer] → persist_message
        """
        # 1. Load session context (prior conversation history)
        state = await self._load_session_context(state)

        # 2. Check scope
        state = await self._check_scope(state)

        if state.scope_check_passed:
            # 3. Run agent
            agent_raw_output: dict[str, Any] | None = None
            cost_limited = False
            try:
                agent_raw_output = await self._run_qa_analyst(state)
            except WorkflowCostLimitError as exc:
                logger.warning(
                    "QAWorkflow cost ceiling hit for session=%s: %s",
                    state.session_id,
                    exc,
                )
                cost_limited = True
                agent_raw_output = {}  # empty — build partial answer

            # 4. Build response
            state = self._build_response(state, agent_raw_output or {}, cost_limited)
        # else: _check_scope already wrote the out-of-scope answer to state.answer

        # 5. Persist messages + episodic memory
        state = await self._persist_message(state)

        return state

    # ── Node: load_session_context ────────────────────────────────────────────

    async def _load_session_context(
        self, state: QAWorkflowState
    ) -> QAWorkflowState:
        """Load prior messages from QARepository to populate conversation_history."""
        try:
            messages = await self._qa_repo.get_messages(
                session_id=state.session_id,
                tenant_id=state.tenant_id,
            )
            # Convert to conversation history format
            history = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            state = state.model_copy(update={"conversation_history": history})
        except Exception as exc:
            logger.warning(
                "Failed to load session context for session=%s: %s",
                state.session_id, exc
            )
        return state

    # ── Node: check_scope ─────────────────────────────────────────────────────

    async def _check_scope(self, state: QAWorkflowState) -> QAWorkflowState:
        """Run QAScopeGuard and set scope_check_passed on state.

        If out of scope: write suggestion directly to state.answer.
        """
        result: ScopeCheckResult = await self._scope_guard.check(
            question=state.question,
            tenant_id=state.tenant_id,
        )

        if result.in_scope:
            return state.model_copy(update={"scope_check_passed": True})

        # Out of scope — build the answer from the suggestion directly
        suggestion = result.suggestion or (
            "This question references companies not in your portfolio or watchlist."
        )
        out_of_scope_answer = QAAnswer(
            answer_text=suggestion,
            sources=[],
            confidence=1.0,  # scope check is deterministic
            cost_usd=0.0,
            cost_limited=False,
        )
        return state.model_copy(
            update={
                "scope_check_passed": False,
                "out_of_scope_suggestion": suggestion,
                "answer": out_of_scope_answer,
            }
        )

    # ── Node: run_qa_analyst ──────────────────────────────────────────────────

    async def _run_qa_analyst(
        self, state: QAWorkflowState
    ) -> dict[str, Any]:
        """Invoke the qa-analyst agent and return raw output dict.

        Raises:
            WorkflowCostLimitError: if the cost ceiling is exceeded.
        """
        return await self._agent_fn(state)

    # ── Node: build_response ──────────────────────────────────────────────────

    def _build_response(
        self,
        state: QAWorkflowState,
        agent_output: dict[str, Any],
        cost_limited: bool,
    ) -> QAWorkflowState:
        """Use QAResponseBuilder to build a typed QAAnswer from agent output."""
        answer = self._response_builder.build(
            agent_output=agent_output,
            cost_limited=cost_limited,
            accumulated_cost=state.cost_usd,
        )
        return state.model_copy(update={"answer": answer})

    # ── Node: persist_message ─────────────────────────────────────────────────

    async def _persist_message(self, state: QAWorkflowState) -> QAWorkflowState:
        """Persist user question + assistant answer and write episodic memory.

        Writes:
          1. QAMessage (role='user') — the original question.
          2. QAMessage (role='assistant') — the built QAAnswer.
          3. WorkflowRun row in episodic memory (workflow_type='qa').
          4. AgentInvocation row in episodic memory (when scope passed).
        """
        answer = state.answer

        # 1. Persist user message
        user_msg = QAMessage(
            session_id=state.session_id,
            tenant_id=state.tenant_id,
            role="user",
            content=state.question,
        )
        await self._qa_repo.append_message(user_msg)

        # 2. Persist assistant message
        assistant_msg = QAMessage(
            session_id=state.session_id,
            tenant_id=state.tenant_id,
            role="assistant",
            content=answer.answer_text if answer else "",
            sources=[s.model_dump() for s in answer.sources] if answer else None,
            confidence=answer.confidence if answer else None,
            cost_usd=answer.cost_usd if answer else None,
            cost_limited=answer.cost_limited if answer else False,
        )
        await self._qa_repo.append_message(assistant_msg)

        # 3. Write episodic workflow_run
        try:
            await self._episodic_repo.append_workflow_run(
                WorkflowRunCreate(
                    workflow_type="qa",
                    tenant_id=state.tenant_id,
                    cost_usd=answer.cost_usd if answer else 0.0,
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to write episodic workflow_run for QA session=%s: %s",
                state.session_id, exc
            )

        # 4. Write agent_invocation row (only if scope passed and agent ran)
        if state.scope_check_passed and answer is not None:
            try:
                await self._episodic_repo.append_agent_invocation(
                    AgentInvocationCreate(
                        workflow_id=state.workflow_id,
                        agent_role_id="qa-analyst",
                        model_used="claude-opus-4-7",
                        cost_usd=answer.cost_usd,
                        confidence=answer.confidence,
                        tools_called=[],
                    )
                )
            except Exception as exc:
                logger.error(
                    "Failed to write agent_invocation for QA session=%s: %s",
                    state.session_id, exc
                )

        return state
