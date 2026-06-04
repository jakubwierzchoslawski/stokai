"""
FeedbackRepository — SQLAlchemy 2.0 async implementation of IFeedbackRepository.

All writes are INSERT-only (no updates; feedback is immutable once submitted).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.interfaces.i_feedback_repository import IFeedbackRepository
from src.ai.memory.models.feedback_models import UserFeedback as UserFeedbackORM
from src.ai.memory.schemas.feedback_schemas import UserFeedback, UserFeedbackCreate


class FeedbackRepository(IFeedbackRepository):
    """SQLAlchemy 2.0 async repository for Layer 4 user feedback."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append_feedback(self, feedback: UserFeedbackCreate) -> UserFeedback:
        """INSERT a new user_feedback row."""
        orm = UserFeedbackORM(
            feedback_id=uuid4(),
            tenant_id=feedback.tenant_id,
            report_id=feedback.report_id,
            recommendation_id=feedback.recommendation_id,
            feedback_type=feedback.feedback_type.value
            if hasattr(feedback.feedback_type, "value")
            else feedback.feedback_type,
            feedback_text=feedback.feedback_text,
            user_edit=feedback.user_edit,
            reviewer_id=feedback.reviewer_id,
            source=feedback.source.value
            if hasattr(feedback.source, "value")
            else feedback.source,
            submitted_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return UserFeedback.model_validate(orm)

    async def list_since(
        self,
        since: datetime,
        tenant_id: UUID | None = None,
    ) -> list[UserFeedback]:
        """Return feedback submitted after `since`."""
        stmt = select(UserFeedbackORM).where(UserFeedbackORM.submitted_at > since)
        if tenant_id is not None:
            stmt = stmt.where(UserFeedbackORM.tenant_id == tenant_id)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [UserFeedback.model_validate(r) for r in rows]

    async def get_feedback_for_report(self, report_id: UUID) -> list[UserFeedback]:
        """Return all feedback for the given report_id."""
        stmt = select(UserFeedbackORM).where(
            UserFeedbackORM.report_id == report_id
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [UserFeedback.model_validate(r) for r in rows]
