"""Tests for ProfileService (TDD — written before implementation)."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from src.scoring.profile_service import ProfileService, BUILTIN_PROFILE_VALUE_INVESTOR
from src.scoring.schemas.scoring_profile import ProfileIndicatorWeight, ScoringProfileRecord
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.repositories.company_score_repo import compute_inputs_hash

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
COMPANY_ID = uuid4()
INDICATOR_A_ID = uuid4()
INDICATOR_B_ID = uuid4()
PROFILE_ID = uuid4()


def _make_profile(
    profile_id: UUID | None = None,
    indicators: list[ProfileIndicatorWeight] | None = None,
    is_builtin: bool = False,
) -> ScoringProfileRecord:
    return ScoringProfileRecord(
        profile_id=profile_id or PROFILE_ID,
        tenant_id=TENANT_ID,
        name="Test Profile",
        indicators=indicators or [],
        is_builtin=is_builtin,
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _make_score(score: float, indicator_id: UUID) -> CompanyScoreRecord:
    return CompanyScoreRecord.new(
        company_id=COMPANY_ID,
        indicator_id=indicator_id,
        tenant_id=TENANT_ID,
        raw_value=score,
        score=score,
        inputs_hash=compute_inputs_hash({"score": score}),
    )


def _make_service(
    profile: ScoringProfileRecord | None = None,
    scores: dict[UUID, float] | None = None,
) -> ProfileService:
    profile_repo = AsyncMock()
    profile_repo.get_by_id = AsyncMock(return_value=profile or _make_profile())
    profile_repo.list_by_tenant = AsyncMock(return_value=[profile] if profile else [])
    profile_repo.save = AsyncMock(side_effect=lambda r: r)

    score_repo = AsyncMock()

    if scores:
        async def get_current(company_id, indicator_id):
            s = scores.get(indicator_id)
            if s is None:
                return None
            return _make_score(s, indicator_id)
        score_repo.get_current = get_current
    else:
        score_repo.get_current = AsyncMock(return_value=None)

    indicator_repo = AsyncMock()
    indicator_repo.list_by_tenant = AsyncMock(return_value=[])

    return ProfileService(profile_repo, score_repo, indicator_repo)


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_get_profile_returns_record_with_indicators(self):
        indicators = [
            ProfileIndicatorWeight(indicator_id=INDICATOR_A_ID, weight=0.6),
            ProfileIndicatorWeight(indicator_id=INDICATOR_B_ID, weight=0.4),
        ]
        profile = _make_profile(indicators=indicators)
        service = _make_service(profile=profile)

        result = await service.get_profile(PROFILE_ID, TENANT_ID)
        assert result is not None
        assert len(result.indicators) == 2


class TestCompositeScore:
    @pytest.mark.asyncio
    async def test_composite_aggregates_weighted_scores(self):
        """Composite = weighted average of company_score rows; weights normalized to 1.0."""
        indicators = [
            ProfileIndicatorWeight(indicator_id=INDICATOR_A_ID, weight=0.6),
            ProfileIndicatorWeight(indicator_id=INDICATOR_B_ID, weight=0.4),
        ]
        profile = _make_profile(indicators=indicators)
        scores = {INDICATOR_A_ID: 80.0, INDICATOR_B_ID: 60.0}
        service = _make_service(profile=profile, scores=scores)

        result = await service.compute_composite_score(COMPANY_ID, PROFILE_ID, TENANT_ID)

        # Weights: 0.6 + 0.4 = 1.0 (already normalized)
        # Composite = 80 * 0.6 + 60 * 0.4 = 48 + 24 = 72
        assert result is not None
        assert result == pytest.approx(72.0)

    @pytest.mark.asyncio
    async def test_switching_profile_does_not_recompute(self):
        """Switching profile reads existing scores, does not trigger re-evaluation."""
        indicators = [ProfileIndicatorWeight(indicator_id=INDICATOR_A_ID, weight=1.0)]
        profile = _make_profile(indicators=indicators)
        scores = {INDICATOR_A_ID: 75.0}
        service = _make_service(profile=profile, scores=scores)

        result = await service.compute_composite_score(COMPANY_ID, PROFILE_ID, TENANT_ID)
        assert result == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_weights_normalized_to_sum_1(self):
        """Weights not summing to 1.0 are normalized before compositing."""
        # Weights: 3 and 1 → normalized to 0.75 and 0.25
        indicators = [
            ProfileIndicatorWeight(indicator_id=INDICATOR_A_ID, weight=3.0),
            ProfileIndicatorWeight(indicator_id=INDICATOR_B_ID, weight=1.0),
        ]
        profile = _make_profile(indicators=indicators)
        scores = {INDICATOR_A_ID: 80.0, INDICATOR_B_ID: 40.0}
        service = _make_service(profile=profile, scores=scores)

        result = await service.compute_composite_score(COMPANY_ID, PROFILE_ID, TENANT_ID)
        # Expected: 80 * 0.75 + 40 * 0.25 = 60 + 10 = 70
        assert result is not None
        assert result == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_no_scores_returns_none(self):
        """If no company_score rows → composite returns None."""
        indicators = [ProfileIndicatorWeight(indicator_id=INDICATOR_A_ID, weight=1.0)]
        profile = _make_profile(indicators=indicators)
        service = _make_service(profile=profile, scores={})

        result = await service.compute_composite_score(COMPANY_ID, PROFILE_ID, TENANT_ID)
        assert result is None


class TestBuiltinProfiles:
    @pytest.mark.asyncio
    async def test_seed_creates_builtin_profiles_if_absent(self):
        """Built-in profiles seeded on startup if absent."""
        service = _make_service()
        service._profile_repo.list_by_tenant = AsyncMock(return_value=[])

        indicator_map = {
            "pe_ratio_score": uuid4(),
            "debt_to_equity_score": uuid4(),
            "roe_score": uuid4(),
        }

        seeded = await service.seed_builtin_profiles(TENANT_ID, indicator_map)
        assert len(seeded) >= 1  # at least VALUE_INVESTOR seeded
        assert any(p.name == "VALUE_INVESTOR" for p in seeded)

    @pytest.mark.asyncio
    async def test_seed_skips_existing_builtin_profiles(self):
        """If built-in profiles already present, seed skips them."""
        existing = _make_profile(is_builtin=True)
        existing.name = "VALUE_INVESTOR"
        service = _make_service(profile=existing)
        service._profile_repo.list_by_tenant = AsyncMock(return_value=[existing])

        indicator_map = {
            "pe_ratio_score": uuid4(),
            "debt_to_equity_score": uuid4(),
            "roe_score": uuid4(),
        }

        seeded = await service.seed_builtin_profiles(TENANT_ID, indicator_map)
        # VALUE_INVESTOR already exists — should not be seeded again
        names_seeded = [p.name for p in seeded]
        assert "VALUE_INVESTOR" not in names_seeded
