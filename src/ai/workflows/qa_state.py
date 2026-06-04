"""
ai.workflows.qa_state — QAWorkflowState for PLAN-F-027.

PLAN-F-027 TASK-003

QAWorkflowState extends the base WorkflowState with Q&A-specific fields.
It is Pydantic-serializable for LangGraph PG checkpointing.

Key fields:
  session_id            — UUID of the QASession row being built.
  question              — The user's current question.
  conversation_history  — List of prior messages for multi-turn context.
  answer                — The QAAnswer once built (None until built).
  scope_check_passed    — Whether the scope guard passed.
  out_of_scope_suggestion — Set by scope guard when out of scope.

Note: WorkflowState.company_id is nullable here because Q&A sessions span
multiple companies. We set it to None by default.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from src.ai.qa.response_builder import QAAnswer
from src.ai.workflows.state import WorkflowState, WorkflowType


class QAWorkflowState(WorkflowState):
    """
    LangGraph state for the Q&A workflow.

    Inherits all WorkflowState fields (workflow_id, tenant_id, user_id, etc.)
    and adds Q&A-specific fields.

    Pydantic v2 model — all fields are serializable to JSON for LangGraph
    PG checkpointing (no non-serializable types).
    """

    # Q&A-specific fields
    session_id: UUID
    question: str

    # Multi-turn conversation history: [{"role": "user"|"assistant", "content": "..."}]
    conversation_history: list[dict[str, str]] = Field(default_factory=list)

    # Set by build_response node after agent completes
    answer: QAAnswer | None = None

    # Set by check_scope node
    scope_check_passed: bool = False
    out_of_scope_suggestion: str | None = None

    @classmethod
    def create(
        cls,
        session_id: UUID,
        question: str,
        tenant_id: UUID,
        user_id: UUID,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> "QAWorkflowState":
        """Factory: build a fresh QAWorkflowState for a new Q&A turn.

        Sets workflow_type=QA and provides sensible defaults.
        company_id is None (Q&A spans multiple companies).
        """
        from src.ai.workflows.state import WorkflowType, WorkflowStatus

        return cls(
            workflow_id=uuid4(),
            workflow_type=WorkflowType.QA,
            tenant_id=tenant_id,
            user_id=user_id,
            company_id=None,
            started_at=datetime.now(tz=timezone.utc),
            session_id=session_id,
            question=question,
            conversation_history=conversation_history or [],
        )
