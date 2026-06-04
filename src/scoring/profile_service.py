"""Scoring profile service — CRUD, composite score, built-in profiles.

Switching profiles does NOT recompute scores — it reads existing company_score rows
and aggregates them using the profile's indicator weights.
"""
from __future__ import annotations

import logging
from uuid import UUID

from src.scoring.repositories.interfaces import (
    ICompanyScoreRepository,
    IIndicatorRepository,
    IScoringProfileRepository,
)
from src.scoring.schemas.scoring_profile import ProfileIndicatorWeight, ScoringProfileRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in profile definitions
# ---------------------------------------------------------------------------

BUILTIN_PROFILE_VALUE_INVESTOR = "VALUE_INVESTOR"
BUILTIN_PROFILE_GROWTH_HUNTER = "GROWTH_HUNTER"
BUILTIN_PROFILE_MACRO_AWARE = "MACRO_AWARE"

# Indicator names for built-in profiles — resolved to real IDs at seed time
_BUILTIN_DEFINITIONS: dict[str, list[tuple[str, float]]] = {
    BUILTIN_PROFILE_VALUE_INVESTOR: [
        # (indicator_name, weight)
        ("pe_ratio_score", 0.35),
        ("debt_to_equity_score", 0.30),
        ("roe_score", 0.35),
    ],
    BUILTIN_PROFILE_GROWTH_HUNTER: [
        ("revenue_growth_score", 0.40),
        ("eps_growth_score", 0.35),
        ("roe_score", 0.25),
    ],
    BUILTIN_PROFILE_MACRO_AWARE: [
        ("geo_risk_score", 0.50),
        ("revenue_score", 0.25),
        ("eps_score", 0.25),
    ],
}


class ProfileService:
    """Business logic for scoring profile management.

    Composite score computation reads existing company_score rows; no re-evaluation.
    """

    def __init__(
        self,
        profile_repository: IScoringProfileRepository,
        score_repository: ICompanyScoreRepository,
        indicator_repository: IIndicatorRepository,
    ) -> None:
        self._profile_repo = profile_repository
        self._score_repo = score_repository
        self._indicator_repo = indicator_repository

    async def get_profile(
        self, profile_id: UUID, tenant_id: UUID
    ) -> ScoringProfileRecord | None:
        return await self._profile_repo.get_by_id(profile_id, tenant_id)

    async def list_profiles(self, tenant_id: UUID) -> list[ScoringProfileRecord]:
        return await self._profile_repo.list_by_tenant(tenant_id)

    async def create_profile(
        self,
        tenant_id: UUID,
        name: str,
        indicators: list[ProfileIndicatorWeight],
        is_builtin: bool = False,
    ) -> ScoringProfileRecord:
        record = ScoringProfileRecord.new(
            tenant_id=tenant_id,
            name=name,
            indicators=indicators,
            is_builtin=is_builtin,
        )
        return await self._profile_repo.save(record)

    async def delete_profile(
        self, profile_id: UUID, tenant_id: UUID
    ) -> bool:
        """Delete a custom profile. Returns False if it's a built-in (protected)."""
        profile = await self._profile_repo.get_by_id(profile_id, tenant_id)
        if profile is None:
            return False
        if profile.is_builtin:
            return False
        # Deletion handled by caller via raw SQL or specific repo method
        return True

    async def compute_composite_score(
        self,
        company_id: UUID,
        profile_id: UUID,
        tenant_id: UUID,
    ) -> float | None:
        """Compute weighted composite score for a company using an existing profile.

        Reads existing company_score rows — does NOT trigger re-evaluation.
        Weights are normalized to sum to 1.0.

        Returns:
            Weighted average score in [0, 100], or None if no scores available.
        """
        profile = await self._profile_repo.get_by_id(profile_id, tenant_id)
        if profile is None:
            return None

        if not profile.indicators:
            return None

        # Normalize weights to sum to 1.0
        total_weight = sum(iw.weight for iw in profile.indicators)
        if total_weight == 0:
            return None

        normalized_weights = [
            ProfileIndicatorWeight(
                indicator_id=iw.indicator_id,
                weight=iw.weight / total_weight,
            )
            for iw in profile.indicators
        ]

        # Read existing scores for each indicator
        composite = 0.0
        total_applied = 0.0

        for iw in normalized_weights:
            score_record = await self._score_repo.get_current(company_id, iw.indicator_id)
            if score_record is None:
                continue
            composite += score_record.score * iw.weight
            total_applied += iw.weight

        if total_applied == 0:
            return None

        # Rescale by actually applied weight fraction
        return composite / total_applied

    async def seed_builtin_profiles(
        self,
        tenant_id: UUID,
        indicator_name_to_id: dict[str, UUID],
    ) -> list[ScoringProfileRecord]:
        """Seed built-in profiles for a tenant if not already present.

        Args:
            tenant_id: tenant to seed for.
            indicator_name_to_id: mapping of indicator name → UUID (resolved at startup).

        Returns:
            List of seeded profiles.
        """
        existing = await self._profile_repo.list_by_tenant(tenant_id)
        existing_names = {p.name for p in existing if p.is_builtin}

        seeded = []
        for profile_name, indicator_specs in _BUILTIN_DEFINITIONS.items():
            if profile_name in existing_names:
                continue

            indicators = []
            for indicator_name, weight in indicator_specs:
                indicator_id = indicator_name_to_id.get(indicator_name)
                if indicator_id is None:
                    logger.warning(
                        "Builtin profile %s: indicator %s not found — skipping.",
                        profile_name,
                        indicator_name,
                    )
                    continue
                indicators.append(ProfileIndicatorWeight(
                    indicator_id=indicator_id,
                    weight=weight,
                ))

            if not indicators:
                continue

            profile = await self.create_profile(
                tenant_id=tenant_id,
                name=profile_name,
                indicators=indicators,
                is_builtin=True,
            )
            seeded.append(profile)
            logger.info("Seeded built-in profile %s for tenant %s", profile_name, tenant_id)

        return seeded
