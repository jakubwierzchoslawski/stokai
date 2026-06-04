"""Tests for IndicatorService (TDD — written before implementation)."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from src.scoring.indicator_service import DslValidationError, DiffResult, IndicatorService
from src.scoring.dsl.validator import ValidationResult
from src.scoring.schemas.indicator import IndicatorRecord, IndicatorVersionRecord

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_indicator(formula_dsl: str = "revenue", version: int = 1) -> IndicatorRecord:
    return IndicatorRecord(
        indicator_id=uuid4(),
        tenant_id=TENANT_ID,
        name="Test Indicator",
        formula_dsl=formula_dsl,
        normalization_mode="percentile",
        normalization_config={},
        direction="higher_better",
        geo_weight=0.0,
        version=version,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _make_version(indicator: IndicatorRecord) -> IndicatorVersionRecord:
    return IndicatorVersionRecord(
        version_id=uuid4(),
        indicator_id=indicator.indicator_id,
        tenant_id=TENANT_ID,
        version=indicator.version,
        formula_dsl=indicator.formula_dsl,
        diff_tokens=[],
        created_at=datetime.utcnow(),
    )


def _make_service(
    indicator: IndicatorRecord | None = None,
    validation_valid: bool = True,
    validation_errors: list[str] | None = None,
) -> tuple[IndicatorService, AsyncMock, MagicMock]:
    repo = AsyncMock()

    if indicator:
        saved = IndicatorRecord(**indicator.__dict__.copy())
        saved.version = indicator.version + 1 if indicator.version > 1 else 1
        repo.get_by_id = AsyncMock(return_value=indicator)
        repo.save = AsyncMock(return_value=indicator)
        repo.list_versions = AsyncMock(return_value=[_make_version(indicator)])
        repo.get_version = AsyncMock(return_value=_make_version(indicator))
    else:
        new_ind = _make_indicator()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.save = AsyncMock(return_value=new_ind)
        repo.list_versions = AsyncMock(return_value=[])
        repo.get_version = AsyncMock(return_value=None)

    repo.list_by_tenant = AsyncMock(return_value=[])

    validator = AsyncMock()
    valid_result = ValidationResult(valid=validation_valid, errors=validation_errors or [])
    validator.validate = AsyncMock(return_value=valid_result)

    service = IndicatorService(repo, validator)
    return service, repo, validator


class TestCreateIndicator:
    @pytest.mark.asyncio
    async def test_create_validates_dsl_before_saving(self):
        service, repo, validator = _make_service()
        new_ind = _make_indicator(formula_dsl="revenue * 0.5")
        repo.save = AsyncMock(return_value=new_ind)

        result = await service.create_indicator(
            tenant_id=TENANT_ID,
            name="Test",
            formula_dsl="revenue * 0.5",
        )

        validator.validate.assert_called_once()
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_returns_indicator_with_version_1(self):
        service, repo, validator = _make_service()
        saved_ind = _make_indicator(formula_dsl="revenue", version=1)
        repo.save = AsyncMock(return_value=saved_ind)

        result = await service.create_indicator(
            tenant_id=TENANT_ID,
            name="Test",
            formula_dsl="revenue",
        )
        assert result.version == 1

    @pytest.mark.asyncio
    async def test_create_raises_on_invalid_dsl(self):
        service, repo, validator = _make_service(
            validation_valid=False,
            validation_errors=["Unknown parameter: bad_param"],
        )
        with pytest.raises(DslValidationError) as exc_info:
            await service.create_indicator(
                tenant_id=TENANT_ID,
                name="Test",
                formula_dsl="bad_param * 0.5",
            )
        assert "bad_param" in str(exc_info.value.errors)
        repo.save.assert_not_called()


class TestUpdateIndicator:
    @pytest.mark.asyncio
    async def test_update_saves_new_version(self):
        indicator = _make_indicator(formula_dsl="revenue", version=1)
        service, repo, validator = _make_service(indicator=indicator)

        v2 = IndicatorRecord(**indicator.__dict__.copy())
        v2.version = 2
        v2.formula_dsl = "revenue * 0.5 + net_income"
        repo.save = AsyncMock(return_value=v2)

        updated = await service.update_indicator(
            indicator_id=indicator.indicator_id,
            tenant_id=TENANT_ID,
            formula_dsl="revenue * 0.5 + net_income",
        )
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_versions_returns_two_after_update(self):
        indicator = _make_indicator(formula_dsl="revenue", version=1)
        service, repo, validator = _make_service(indicator=indicator)

        v1 = _make_version(indicator)
        v2_ind = _make_indicator(formula_dsl="revenue * 2", version=2)
        v2_ind.indicator_id = indicator.indicator_id
        v2 = _make_version(v2_ind)
        repo.list_versions = AsyncMock(return_value=[v1, v2])

        versions = await service.list_versions(indicator.indicator_id)
        assert len(versions) == 2


class TestGetDiff:
    @pytest.mark.asyncio
    async def test_diff_shows_added_removed_unchanged(self):
        indicator = _make_indicator(formula_dsl="revenue", version=2)
        service, repo, validator = _make_service(indicator=indicator)

        v1_record = IndicatorVersionRecord(
            version_id=uuid4(),
            indicator_id=indicator.indicator_id,
            tenant_id=TENANT_ID,
            version=1,
            formula_dsl="revenue",
            diff_tokens=[],
            created_at=datetime.utcnow(),
        )
        v2_record = IndicatorVersionRecord(
            version_id=uuid4(),
            indicator_id=indicator.indicator_id,
            tenant_id=TENANT_ID,
            version=2,
            formula_dsl="revenue * 0.5",
            diff_tokens=[],
            created_at=datetime.utcnow(),
        )

        repo.get_version = AsyncMock(side_effect=lambda ind_id, v: v1_record if v == 1 else v2_record)

        diff = await service.get_diff(indicator.indicator_id, v1=1, v2=2)
        assert isinstance(diff, DiffResult)
        # "revenue" is unchanged; "*" and "0.5" are added
        assert "revenue" in diff.unchanged_tokens
        assert "*" in diff.added_tokens
        assert "0.5" in diff.added_tokens


class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_creates_new_version_with_v1_dsl(self):
        original_dsl = "revenue"
        indicator = _make_indicator(formula_dsl="revenue * 0.9", version=2)
        service, repo, validator = _make_service(indicator=indicator)

        v1_record = IndicatorVersionRecord(
            version_id=uuid4(),
            indicator_id=indicator.indicator_id,
            tenant_id=TENANT_ID,
            version=1,
            formula_dsl=original_dsl,
            diff_tokens=[],
            created_at=datetime.utcnow(),
        )
        repo.get_version = AsyncMock(return_value=v1_record)

        rolled_back = IndicatorRecord(**indicator.__dict__.copy())
        rolled_back.version = 3
        rolled_back.formula_dsl = original_dsl
        repo.save = AsyncMock(return_value=rolled_back)

        result = await service.rollback(
            indicator_id=indicator.indicator_id,
            tenant_id=TENANT_ID,
            target_version=1,
        )

        repo.save.assert_called_once()
        # The saved record should have the original DSL
        call_args = repo.save.call_args[0][0]
        assert call_args.formula_dsl == original_dsl
