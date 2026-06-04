"""Tests for the DSL semantic validator."""
from __future__ import annotations

import pytest
from uuid import UUID
from unittest.mock import AsyncMock

from src.scoring.dsl.tokenizer import tokenize
from src.scoring.dsl.parser import parse
from src.scoring.dsl.validator import DslValidator, ValidationResult

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")

KNOWN_PARAMS = ["revenue", "net_income", "pe_ratio", "roe", "price", "eps", "debt_to_equity"]


def _make_catalog(params: list[str] | None = None):
    catalog = AsyncMock()
    catalog.get_enabled_parameters = AsyncMock(return_value=params or KNOWN_PARAMS)
    return catalog


def _parse(formula: str):
    return parse(tokenize(formula))


class TestValidValidator:
    @pytest.mark.asyncio
    async def test_valid_simple_formula(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("revenue * 0.5"), TENANT_ID)
        assert result.valid is True
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_builtin_functions_always_valid(self):
        validator = DslValidator(_make_catalog())
        for fn in ["IF", "RANK", "ZSCORE", "PERCENTILE", "MIN", "MAX", "ABS", "LOG"]:
            result = await validator.validate(
                _parse(f"{fn}(revenue)"), TENANT_ID
            )
            assert result.valid is True, f"Expected {fn} to be valid"

    @pytest.mark.asyncio
    async def test_builtin_functions_case_insensitive(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("abs(revenue)"), TENANT_ID)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_timeseries_valid(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("price[-1] / price[-5]"), TENANT_ID)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_conditional_expr_valid(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("IF(pe_ratio < 15, 1, 0)"), TENANT_ID)
        assert result.valid is True


class TestInvalidValidator:
    @pytest.mark.asyncio
    async def test_unknown_parameter(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("unknown_param * 0.5"), TENANT_ID)
        assert result.valid is False
        assert any("unknown_param" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_unknown_function(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("MY_CUSTOM_FN(revenue)"), TENANT_ID)
        assert result.valid is False
        assert any("MY_CUSTOM_FN" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_timeseries_unknown_parameter(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("bad_param[-1]"), TENANT_ID)
        assert result.valid is False
        assert any("bad_param" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_multiple_errors_accumulated(self):
        validator = DslValidator(_make_catalog())
        result = await validator.validate(_parse("bad1 + bad2"), TENANT_ID)
        assert result.valid is False
        assert len(result.errors) == 2
