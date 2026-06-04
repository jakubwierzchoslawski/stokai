"""
briefs.services.brief_feedback_service — BriefFeedbackService.

Validates feedback payload, calls IFeedbackRepository.append_feedback(),
and on edit feedback additionally writes a GoldenDatasetCandidate row.

PLAN-F-026 TASK-002
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError

from src.ai.memory.interfaces.i_feedback_repository import IFeedbackRepository
from src.ai.memory.schemas.feedback_schemas import FeedbackSource, FeedbackType, UserFeedbackCreate
from src.briefs.interfaces.i_golden_dataset_repository import IGoldenDatasetRepository
from src.briefs.schemas.brief_schemas import BriefFeedbackCreate, GoldenDatasetCandidateCreate

logger = logging.getLogger(__name__)

_VALID_FEEDBACK_TYPES = {"thumbs_up", "thumbs_down", "edit"}


class BriefFeedbackValidationError(ValueError):
    """Raised when feedback payload fails validation rules."""


class BriefFeedbackService:
    """Service for submitting brief feedback.

    Constructor-injected IFeedbackRepository (from PLAN-F-015) and
    IGoldenDatasetRepository (defined in this plan).
    """

    def __init__(
        self,
        feedback_repository: IFeedbackRepository,
        golden_dataset_repository: IGoldenDatasetRepository,
    ) -> None:
        self._feedback_repo = feedback_repository
        self._golden_repo = golden_dataset_repository

    async def submit_feedback(
        self,
        brief_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        payload: BriefFeedbackCreate,
        original_content: str = "",
    ) -> UUID:
        """Persist feedback and, for edit type, a GoldenDatasetCandidate.

        Returns the feedback_id UUID.

        Raises BriefFeedbackValidationError for invalid payloads.
        """
        feedback_type = payload.feedback_type

        if feedback_type not in _VALID_FEEDBACK_TYPES:
            raise BriefFeedbackValidationError(
                f"Invalid feedback_type: {feedback_type!r}. "
                f"Must be one of: {_VALID_FEEDBACK_TYPES}"
            )

        if feedback_type == "edit":
            if not payload.correction or not payload.correction.strip():
                raise BriefFeedbackValidationError(
                    "correction must be non-null and non-empty when feedback_type='edit'"
                )

        # Map brief feedback type to FeedbackType enum
        # "edit" from brief widget maps to "edit_approve" in the memory layer
        _FEEDBACK_TYPE_MAP: dict[str, FeedbackType] = {
            "thumbs_up": FeedbackType.THUMBS_UP,
            "thumbs_down": FeedbackType.THUMBS_DOWN,
            "edit": FeedbackType.EDIT_APPROVE,
        }
        feedback_type_enum = _FEEDBACK_TYPE_MAP[feedback_type]

        feedback_create = UserFeedbackCreate(
            tenant_id=tenant_id,
            report_id=brief_id,
            recommendation_id=None,
            feedback_type=feedback_type_enum,
            feedback_text=None,
            user_edit=payload.correction,
            reviewer_id=user_id,
            source=FeedbackSource.IN_APP,
        )
        feedback = await self._feedback_repo.append_feedback(feedback_create)

        if feedback_type == "edit":
            candidate = GoldenDatasetCandidateCreate(
                tenant_id=tenant_id,
                brief_id=brief_id,
                user_id=user_id,
                original_content=original_content,
                correction=payload.correction,
            )
            await self._golden_repo.create_candidate(candidate)

        return feedback.feedback_id
