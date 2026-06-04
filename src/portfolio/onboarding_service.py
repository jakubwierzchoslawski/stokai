"""
portfolio.onboarding_service — OnboardingService.

Manages user onboarding state, scoring profile selection, and skip flag.
Persists onboarding state in the user.settings JSONB column.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


# ── DTOs ──────────────────────────────────────────────────────────────────────


class OnboardingState(BaseModel):
    """Onboarding state returned to the client."""

    is_complete: bool
    skipped: bool
    has_holding: bool
    scoring_profile_id: uuid.UUID | None


# ── Protocols ─────────────────────────────────────────────────────────────────


class IUserSettingsRepository:
    """Protocol for reading and updating user.settings JSONB."""

    async def get_settings(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        ...

    async def update_settings(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        patch: dict[str, Any],
    ) -> None:
        ...


class IHasHoldingChecker:
    """Protocol to check whether a user has any portfolio holding."""

    async def has_any_holding(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        ...


# ── Service ───────────────────────────────────────────────────────────────────


class OnboardingService:
    """Domain service for user onboarding lifecycle.

    Dependencies are injected via the constructor (DIP).
    """

    def __init__(
        self,
        user_settings_repo: IUserSettingsRepository,
        holding_checker: IHasHoldingChecker,
    ) -> None:
        self._settings_repo = user_settings_repo
        self._holding_checker = holding_checker

    async def get_onboarding_state(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OnboardingState:
        """Return the current onboarding state for the user."""
        settings = await self._settings_repo.get_settings(tenant_id, user_id)
        skipped = bool(settings.get("onboarding_skipped", False))
        scoring_profile_id_raw = settings.get("scoring_profile_id")
        scoring_profile_id = (
            uuid.UUID(str(scoring_profile_id_raw)) if scoring_profile_id_raw else None
        )
        has_holding = await self._holding_checker.has_any_holding(tenant_id, user_id)
        is_complete = skipped or has_holding

        return OnboardingState(
            is_complete=is_complete,
            skipped=skipped,
            has_holding=has_holding,
            scoring_profile_id=scoring_profile_id,
        )

    async def select_scoring_profile(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> None:
        """Persist the chosen scoring profile in user.settings."""
        await self._settings_repo.update_settings(
            tenant_id,
            user_id,
            {"scoring_profile_id": str(profile_id)},
        )

    async def mark_skipped(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Set user.settings.onboarding_skipped = true."""
        await self._settings_repo.update_settings(
            tenant_id,
            user_id,
            {"onboarding_skipped": True},
        )

    async def is_onboarding_required(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Return True when has_holding=False AND skipped=False."""
        state = await self.get_onboarding_state(tenant_id, user_id)
        return not state.has_holding and not state.skipped
