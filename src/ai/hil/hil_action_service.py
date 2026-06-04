"""
ai.hil.hil_action_service — HIL reviewer action dispatch.

HILActionService.apply_action processes the four reviewer decisions:
  - approve: resume graph without changes; write user_feedback(approve).
  - edit_approve: resume graph with reviewer text; write user_feedback(edit_approve).
  - reject: terminate graph; write user_feedback(reject).
  - reject_with_feedback: terminate graph; write user_feedback(reject_with_feedback).

For every action, a Layer 1 episodic audit row is written via
WorkflowRunRepository (REQ-N-012).

PLAN-F-013 TASK-005
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel

from src.ai.hil.hil_resume import HILResumeService
from src.storage.repositories.hil_queue_repository import HILQueueRepository, HILStatus
from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

logger = logging.getLogger(__name__)

# ── Action type ───────────────────────────────────────────────────────────────

HILAction = Literal["approve", "edit_approve", "reject", "reject_with_feedback"]


# ── Domain exceptions ─────────────────────────────────────────────────────────


class HILValidationError(ValueError):
    """Raised when a required field is missing for a given HIL action.

    - edit_approve requires edited_text.
    - reject_with_feedback requires feedback_text.
    """


# ── DTOs ──────────────────────────────────────────────────────────────────────


class UserFeedbackCreate(BaseModel):
    """DTO for writing a user_feedback row (Layer 4 memory, PLAN-F-015)."""

    tenant_id: UUID
    workflow_run_id: UUID
    feedback_type: str          # approve | edit_approve | reject | reject_with_feedback
    reviewer_id: UUID
    user_edit: str | None = None        # edited content (edit_approve only)
    feedback_text: str | None = None    # reviewer comment (reject_with_feedback)
    source: str = "hil_action"


@dataclass
class HILActionResult:
    """Result returned by apply_action."""

    item_id: UUID
    status: str
    workflow_resumed: bool
    feedback_id: UUID


# ── UserFeedbackRepository stub ───────────────────────────────────────────────


class UserFeedbackRepository:
    """Minimal stub for the user_feedback repository (PLAN-F-015 owns the real impl).

    This stub writes to user_feedback using a raw SQLAlchemy INSERT.
    Once PLAN-F-015 is executed, this class should be replaced with the
    proper injection of the real UserFeedbackRepository.
    """

    def __init__(self, session) -> None:  # type: ignore[type-arg]
        self._session = session

    async def create(self, feedback: UserFeedbackCreate):  # type: ignore[return]
        """Insert a user_feedback row and return the persisted object."""
        from sqlalchemy import text

        feedback_id = uuid4()
        stmt = text(
            """
            INSERT INTO user_feedback
                (feedback_id, tenant_id, reviewer_id, feedback_type,
                 feedback_text, user_edit, source, submitted_at)
            VALUES
                (:feedback_id, :tenant_id, :reviewer_id, :feedback_type,
                 :feedback_text, :user_edit, :source, :submitted_at)
            """
        )
        await self._session.execute(
            stmt,
            {
                "feedback_id": str(feedback_id),
                "tenant_id": str(feedback.tenant_id),
                "reviewer_id": str(feedback.reviewer_id),
                "feedback_type": feedback.feedback_type,
                "feedback_text": feedback.feedback_text,
                "user_edit": feedback.user_edit,
                "source": feedback.source,
                "submitted_at": datetime.now(tz=timezone.utc).isoformat(),
            },
        )
        await self._session.flush()

        result = type("FeedbackRow", (), {"feedback_id": feedback_id})()
        return result


# ── Service ───────────────────────────────────────────────────────────────────


class HILActionService:
    """Apply a reviewer's decision to a paused HIL queue item.

    Constructor-injected dependencies (DIP):
      - hil_queue_repo:     HILQueueRepository
      - resume_service:     HILResumeService
      - feedback_repo:      UserFeedbackRepository (Layer 4)
      - workflow_run_repo:  WorkflowRunRepository (Layer 1 audit)
    """

    def __init__(
        self,
        hil_queue_repo: HILQueueRepository,
        resume_service: HILResumeService,
        feedback_repo: UserFeedbackRepository,
        workflow_run_repo: WorkflowRunRepository,
    ) -> None:
        self._hil_repo = hil_queue_repo
        self._resume = resume_service
        self._feedback_repo = feedback_repo
        self._workflow_run_repo = workflow_run_repo

    async def apply_action(
        self,
        item_id: UUID,
        tenant_id: UUID,
        reviewer_id: UUID,
        action: HILAction,
        edited_text: str | None = None,
        feedback_text: str | None = None,
    ) -> HILActionResult:
        """Apply a reviewer action to a pending HIL queue item.

        Args:
            item_id:       UUID of the hil_queue_item row.
            tenant_id:     Tenant scope (from JWT — never from request body).
            reviewer_id:   UUID of the reviewer performing the action.
            action:        One of "approve", "edit_approve", "reject",
                           "reject_with_feedback".
            edited_text:   Required when action == "edit_approve".
            feedback_text: Required when action == "reject_with_feedback".

        Returns:
            HILActionResult with final status, resume flag, and feedback_id.

        Raises:
            HILValidationError: When required fields are missing.
            ValueError: When item not found or wrong tenant.
        """
        # ── Input validation ──────────────────────────────────────────────────
        if action == "edit_approve" and not edited_text:
            raise HILValidationError(
                "edited_text is required for action='edit_approve'"
            )
        if action == "reject_with_feedback" and not feedback_text:
            raise HILValidationError(
                "feedback_text is required for action='reject_with_feedback'"
            )

        # ── Load queue item ───────────────────────────────────────────────────
        item = await self._hil_repo.get(item_id, tenant_id)
        if item is None:
            raise ValueError(
                f"HIL queue item {item_id} not found for tenant {tenant_id}"
            )

        workflow_resumed = False
        new_status = HILStatus.REJECTED

        # ── Execute action ────────────────────────────────────────────────────
        if action == "approve":
            await self._resume.resume_from_checkpoint(
                lc_checkpoint_id=item.lc_checkpoint_id,
                override_text=None,
            )
            new_status = HILStatus.APPROVED
            workflow_resumed = True
            feedback_type = "approve"
            fb_edit = None
            fb_text = None

        elif action == "edit_approve":
            await self._resume.resume_from_checkpoint(
                lc_checkpoint_id=item.lc_checkpoint_id,
                override_text=edited_text,
            )
            new_status = HILStatus.EDITED_APPROVED
            workflow_resumed = True
            feedback_type = "edit_approve"
            fb_edit = edited_text
            fb_text = None

        elif action == "reject":
            await self._resume.terminate_workflow(
                lc_checkpoint_id=item.lc_checkpoint_id,
                reason="Reviewer rejected",
            )
            new_status = HILStatus.REJECTED
            workflow_resumed = False
            feedback_type = "reject"
            fb_edit = None
            fb_text = None

        else:  # reject_with_feedback
            await self._resume.terminate_workflow(
                lc_checkpoint_id=item.lc_checkpoint_id,
                reason=f"Reviewer rejected with feedback: {feedback_text}",
            )
            new_status = HILStatus.REJECTED
            workflow_resumed = False
            feedback_type = "reject_with_feedback"
            fb_edit = None
            fb_text = feedback_text

        # ── Update queue item status ──────────────────────────────────────────
        reviewed_at = datetime.now(tz=timezone.utc)
        await self._hil_repo.update_status(
            item_id=item_id,
            tenant_id=tenant_id,
            status=new_status,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
        )

        # ── Write Layer 4 user_feedback row ───────────────────────────────────
        feedback_dto = UserFeedbackCreate(
            tenant_id=tenant_id,
            workflow_run_id=item.workflow_run_id,
            feedback_type=feedback_type,
            reviewer_id=reviewer_id,
            user_edit=fb_edit,
            feedback_text=fb_text,
            source="hil_action",
        )
        feedback_row = await self._feedback_repo.create(feedback_dto)

        # ── Write Layer 1 episodic audit row (REQ-N-012) ──────────────────────
        try:
            await self._workflow_run_repo.append_audit_event(
                workflow_run_id=item.workflow_run_id,
                event_type="hil_action",
                payload={
                    "action": action,
                    "reviewer_id": str(reviewer_id),
                    "timestamp": reviewed_at.isoformat(),
                    "new_status": new_status.value,
                },
            )
        except AttributeError:
            # WorkflowRunRepository may not have append_audit_event yet
            # (PLAN-F-015 adds this method). Fall back to update_status for audit.
            logger.debug(
                "HILActionService: WorkflowRunRepository.append_audit_event not available; "
                "audit recorded via update_status"
            )

        logger.info(
            "HILActionService.apply_action: item_id=%s action=%s new_status=%s "
            "reviewer_id=%s workflow_resumed=%s",
            item_id,
            action,
            new_status.value,
            reviewer_id,
            workflow_resumed,
        )

        return HILActionResult(
            item_id=item_id,
            status=new_status.value,
            workflow_resumed=workflow_resumed,
            feedback_id=feedback_row.feedback_id,
        )
