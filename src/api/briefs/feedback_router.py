"""
api.briefs.feedback_router — FastAPI router for brief feedback submission.

POST /api/v1/briefs/{id}/feedback — submit thumbs-up/down/edit (JWT required)

PLAN-F-026 TASK-004
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.briefs.briefs_schemas import FeedbackApiResponse, FeedbackRequest, FeedbackResponseData
from src.briefs.interfaces.i_brief_service import IBriefService
from src.briefs.schemas.brief_schemas import BriefFeedbackCreate
from src.briefs.services.brief_feedback_service import BriefFeedbackService, BriefFeedbackValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefs", tags=["briefs-feedback"])


def _get_feedback_service() -> BriefFeedbackService:
    """Dependency that resolves BriefFeedbackService with production repositories.

    Tests override this via FastAPI's dependency_overrides.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.ai.memory.repositories.feedback_repository import FeedbackRepository
    from src.briefs.repositories.golden_dataset_repository import GoldenDatasetRepository
    from src.config.settings import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    session = factory()

    feedback_repo = FeedbackRepository(session)
    golden_repo = GoldenDatasetRepository(session)

    return BriefFeedbackService(
        feedback_repository=feedback_repo,
        golden_dataset_repository=golden_repo,
    )


def _get_brief_service_for_feedback() -> IBriefService:
    """Dependency resolving BriefService for content lookup during edit feedback."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.briefs.repositories.brief_repository import BriefRepository
    from src.briefs.services.brief_service import BriefService
    from src.config.settings import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    session = factory()
    repo = BriefRepository(session)
    return BriefService(brief_repository=repo)


@router.post(
    "/{brief_id}/feedback",
    response_model=FeedbackApiResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    brief_id: UUID,
    body: FeedbackRequest,
    current_user: CurrentUser = Depends(get_current_user),
    feedback_service: BriefFeedbackService = Depends(_get_feedback_service),
    brief_service: IBriefService = Depends(_get_brief_service_for_feedback),
) -> FeedbackApiResponse:
    """Submit thumbs-up, thumbs-down, or edit correction for a brief."""
    # Validate feedback_type early — return 422 for edit without correction
    if body.feedback_type == "edit" and (not body.correction or not body.correction.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "correction is required when feedback_type='edit'",
            },
        )

    # Fetch original content for golden dataset (only needed for edit type)
    original_content = ""
    if body.feedback_type == "edit":
        try:
            from src.briefs.services.brief_service import BriefNotFoundError
            projection = await brief_service.get_brief_detail(
                brief_id=brief_id,
                user_id=current_user.user_id,
                tenant_id=current_user.tenant_id,
            )
            original_content = projection.content_html
        except Exception:
            # If we can't fetch content, proceed without it (non-fatal)
            logger.warning("Could not fetch brief content for golden dataset; brief_id=%s", brief_id)

    try:
        payload = BriefFeedbackCreate(
            feedback_type=body.feedback_type,
            correction=body.correction,
        )
        feedback_id = await feedback_service.submit_feedback(
            brief_id=brief_id,
            user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            payload=payload,
            original_content=original_content,
        )
    except BriefFeedbackValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        )

    return FeedbackApiResponse(data=FeedbackResponseData(feedback_id=feedback_id), meta={})
