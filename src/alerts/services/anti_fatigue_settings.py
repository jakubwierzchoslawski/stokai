"""
AntiFatigueSettingsService — read/write user anti-fatigue settings from user.settings JSONB.

Validates: daily_push_limit>=1, dedup_window_minutes>=1,
           overnight quiet hours (start>end OK), start==end raises ValidationError.
Partial update preserves fields not included in the request.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.exceptions import ValidationError
from src.alerts.schemas import AntiFatigueSettingsResponse, UpdateAntiFatigueRequest

logger = logging.getLogger(__name__)

# Defaults when no settings row exists
_DEFAULT_DAILY_PUSH_LIMIT = 20
_DEFAULT_DEDUP_WINDOW_MINUTES = 60


class AntiFatigueSettingsService:
    """Read and write anti-fatigue settings stored in user.settings JSONB.

    Args:
        session: Async SQLAlchemy session (injected by caller).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_update(request: UpdateAntiFatigueRequest) -> None:
        if request.daily_push_limit is not None and request.daily_push_limit < 1:
            raise ValidationError("daily_push_limit must be >= 1")
        if request.dedup_window_minutes is not None and request.dedup_window_minutes < 1:
            raise ValidationError("dedup_window_minutes must be >= 1")
        if (
            request.quiet_hours_start is not None
            and request.quiet_hours_end is not None
            and request.quiet_hours_start == request.quiet_hours_end
        ):
            raise ValidationError(
                "quiet_hours_start and quiet_hours_end must differ (zero-length window)"
            )

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_settings(
        self, *, user_id: UUID, tenant_id: UUID
    ) -> AntiFatigueSettingsResponse:
        """Read anti-fatigue settings from user.settings JSONB.

        Returns defaults if the user has no settings row.
        """
        stmt = text(
            """
            SELECT
                COALESCE((settings->>'daily_push_limit')::INT,          :default_limit)  AS daily_push_limit,
                settings->>'quiet_hours_start'                                           AS quiet_hours_start,
                settings->>'quiet_hours_end'                                             AS quiet_hours_end,
                COALESCE((settings->>'dedup_window_minutes')::INT,       :default_dedup)  AS dedup_window_minutes
            FROM "user"
            WHERE user_id   = :user_id
              AND tenant_id = :tenant_id
            LIMIT 1
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "default_limit": _DEFAULT_DAILY_PUSH_LIMIT,
                "default_dedup": _DEFAULT_DEDUP_WINDOW_MINUTES,
            },
        )
        row = result.mappings().first()
        if row is None:
            return AntiFatigueSettingsResponse(
                daily_push_limit=_DEFAULT_DAILY_PUSH_LIMIT,
                quiet_hours_start=None,
                quiet_hours_end=None,
                dedup_window_minutes=_DEFAULT_DEDUP_WINDOW_MINUTES,
            )
        return AntiFatigueSettingsResponse(
            daily_push_limit=int(row["daily_push_limit"]),
            quiet_hours_start=row["quiet_hours_start"],
            quiet_hours_end=row["quiet_hours_end"],
            dedup_window_minutes=int(row["dedup_window_minutes"]),
        )

    async def update_settings(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        request: UpdateAntiFatigueRequest,
    ) -> AntiFatigueSettingsResponse:
        """Partial-update anti-fatigue settings in user.settings JSONB.

        Only provided fields are changed; others are preserved via jsonb_build_object
        and COALESCE in the SQL.

        Raises:
            ValidationError: if any field violates domain constraints.
        """
        self._validate_update(request)

        stmt = text(
            """
            UPDATE "user"
            SET settings = settings || jsonb_build_object(
                'daily_push_limit',      COALESCE(:daily_push_limit::TEXT,    (settings->>'daily_push_limit')),
                'quiet_hours_start',     COALESCE(:quiet_hours_start,          settings->>'quiet_hours_start'),
                'quiet_hours_end',       COALESCE(:quiet_hours_end,            settings->>'quiet_hours_end'),
                'dedup_window_minutes',  COALESCE(:dedup_window_minutes::TEXT, (settings->>'dedup_window_minutes'))
            )
            WHERE user_id   = :user_id
              AND tenant_id = :tenant_id
            """
        )
        await self._session.execute(
            stmt,
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "daily_push_limit": str(request.daily_push_limit) if request.daily_push_limit is not None else None,
                "quiet_hours_start": request.quiet_hours_start,
                "quiet_hours_end": request.quiet_hours_end,
                "dedup_window_minutes": str(request.dedup_window_minutes) if request.dedup_window_minutes is not None else None,
            },
        )
        logger.info("AntiFatigueSettingsService.update_settings: user=%s", user_id)
        return await self.get_settings(user_id=user_id, tenant_id=tenant_id)
