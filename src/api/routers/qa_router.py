"""
api.routers.qa_router — FastAPI router for Q&A chat session endpoints.

PLAN-F-027 TASK-005

Endpoints:
  POST /api/v1/qa/sessions                              — create session
  POST /api/v1/qa/sessions/{session_id}/messages        — submit question (SSE stream)

Security: JWT auth required on all endpoints (get_current_user).
tenant_id and user_id: extracted from JWT only — never from request body.

SSE stream format:
  data: {"type": "chunk", "text": "..."}\n\n       -- partial text chunks
  data: {"type": "done", "answer": {...}}\n\n        -- final QAAnswer JSON
  data: {"type": "cost_limited", "partial_answer": {...}}\n\n  -- ceiling hit

Note: QAWorkflow runs INLINE (not Celery) for SSE compatibility.
      Accepted MVP scaling limitation — annotated in QAWorkflow docstring.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.auth_deps import CurrentUser, get_current_user
from src.storage.repositories.qa_repository import IQARepository, QASession

logger = logging.getLogger(__name__)

qa_router = APIRouter(prefix="/qa", tags=["qa"])


# ── Dependency stubs ───────────────────────────────────────────────────────────


async def get_qa_repository() -> IQARepository:
    """Provide QARepository. Override in tests via app.dependency_overrides."""
    raise NotImplementedError(
        "get_qa_repository must be overridden in the composition root or tests."
    )


async def get_qa_workflow():
    """Provide QAWorkflow. Override in tests via app.dependency_overrides."""
    raise NotImplementedError(
        "get_qa_workflow must be overridden in the composition root or tests."
    )


# ── Request / response schemas ─────────────────────────────────────────────────


class CreateSessionResponse(BaseModel):
    session_id: UUID


class SubmitMessageRequest(BaseModel):
    question: str


# ── Endpoints ──────────────────────────────────────────────────────────────────


@qa_router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateSessionResponse,
    summary="Create a new Q&A session",
)
async def create_session(
    current_user: CurrentUser = Depends(get_current_user),
    qa_repo: IQARepository = Depends(get_qa_repository),
) -> CreateSessionResponse:
    """Create a new Q&A session for the authenticated user.

    Returns the session_id to use for subsequent message submissions.
    tenant_id and user_id are taken from the JWT — never from the request body.
    """
    new_session = QASession(
        session_id=uuid4(),
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
    )
    persisted = await qa_repo.create_session(new_session)
    return CreateSessionResponse(session_id=persisted.session_id)


@qa_router.post(
    "/sessions/{session_id}/messages",
    summary="Submit a question and stream the Q&A answer (SSE)",
)
async def submit_message(
    session_id: UUID,
    body: SubmitMessageRequest,
    current_user: CurrentUser = Depends(get_current_user),
    qa_repo: IQARepository = Depends(get_qa_repository),
    workflow=Depends(get_qa_workflow),
) -> StreamingResponse:
    """Submit a question to a Q&A session and receive the answer via SSE.

    Validates session ownership (user_id+tenant_id) before execution.
    Runs QAWorkflow INLINE (not Celery) to support SSE streaming.

    SSE events:
      chunk       — partial text token as the answer is built
      done        — final QAAnswer JSON when complete
      cost_limited — when the $0.40 ceiling is hit before completion

    Returns:
        StreamingResponse with text/event-stream media type.

    Raises:
        403: If session_id does not belong to the current user (IDOR prevention).
    """
    # IDOR check: validate session belongs to this user+tenant
    session = await qa_repo.get_session(
        session_id=session_id,
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Session not found or does not belong to this user.",
            },
        )

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events by running QAWorkflow inline."""
        try:
            from src.ai.workflows.qa_state import QAWorkflowState

            state = QAWorkflowState.create(
                session_id=session_id,
                question=body.question,
                tenant_id=current_user.tenant_id,
                user_id=current_user.user_id,
            )

            final_state = await workflow.run(state)
            answer = final_state.answer

            if answer is not None:
                if answer.cost_limited:
                    # Cost ceiling hit — emit cost_limited event
                    payload = json.dumps(
                        {
                            "type": "cost_limited",
                            "partial_answer": answer.model_dump(),
                        }
                    )
                    yield f"data: {payload}\n\n"
                else:
                    # Emit done event with full answer
                    payload = json.dumps(
                        {
                            "type": "done",
                            "answer": answer.model_dump(),
                        }
                    )
                    yield f"data: {payload}\n\n"
            else:
                # No answer produced (should not happen) — emit empty done
                payload = json.dumps({"type": "done", "answer": None})
                yield f"data: {payload}\n\n"

        except Exception as exc:
            logger.error(
                "QA workflow error for session=%s: %s", session_id, exc, exc_info=True
            )
            payload = json.dumps(
                {"type": "error", "message": "An internal error occurred."}
            )
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
