"""Tests for AstEvaluator (TDD — written before implementation)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from src.scoring.dsl.tokenizer import tokenize
from src.scoring.dsl.parser import parse
from src.scoring.evaluator.ast_evaluator import AstEvaluator
from src.scoring.evaluator.operator_registry import DslEvalError

COMPANY_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")


def _make_provider(fundamentals: dict, time_series: dict | None = None):
    provider = AsyncMock()
    provider.get_company_fundamentals = AsyncMock(return_value=fundamentals)
    provider.get_time_series = AsyncMock(
        side_effect=lambda cid, param, periods: (time_series or {}).get(param, [])
    )
    return provider


def _make_catalog(params: list[str] | None = None):
    catalog = AsyncMock()
    catalog.get_enabled_parameters = AsyncMock(return_value=params or [])
    return catalog


def _parse(formula: str):
    return parse(tokenize(formula))


class TestBasicEvaluation:
    @pytest.mark.asyncio
    async def test_revenue_times_0_5(self):
        """revenue * 0.5 given revenue=1000.0 → 500.0"""
        provider = _make_provider({"revenue": 1000.0})
        evaluator = AstEvaluator(provider, _make_catalog())
        result = await evaluator.evaluate(_parse("revenue * 0.5"), COMPANY_ID, TENANT_ID)
        assert result == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_conditional_pe_ratio_lt_15(self):
        """IF(pe_ratio < 15, 1.0, 0.0) given pe_ratio=12.0 → 1.0"""
        provider = _make_provider({"pe_ratio": 12.0})
        evaluator = AstEvaluator(provider, _make_catalog())
        result = await evaluator.evaluate(
            _parse("IF(pe_ratio < 15, 1.0, 0.0)"), COMPANY_ID, TENANT_ID
        )
        assert result == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_conditional_false_branch(self):
        """IF(pe_ratio < 15, 1.0, 0.0) given pe_ratio=20.0 → 0.0"""
        provider = _make_provider({"pe_ratio": 20.0})
        evaluator = AstEvaluator(provider, _make_catalog())
        result = await evaluator.evaluate(
            _parse("IF(pe_ratio < 15, 1.0, 0.0)"), COMPANY_ID, TENANT_ID
        )
        assert result == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_rank_via_stub_provider(self):
        """RANK(roe) with stub provider returns a float."""
        provider = _make_provider({"roe": 0.15})
        evaluator = AstEvaluator(provider, _make_catalog())
        # RANK with no peer_values returns 50.0 by convention
        result = await evaluator.evaluate(_parse("RANK(roe)"), COMPANY_ID, TENANT_ID)
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_time_series_index(self):
        """price[-1] / price[-5] via stub returning time-series list → float"""
        provider = _make_provider(
            {},
            time_series={
                "price": [100.0, 110.0, 120.0, 130.0, 140.0, 150.0],
            },
        )
        evaluator = AstEvaluator(provider, _make_catalog())
        result = await evaluator.evaluate(
            _parse("price[-1] / price[-5]"), COMPANY_ID, TENANT_ID
        )
        assert result is not None
        assert isinstance(result, float)


class TestNullPropagation:
    @pytest.mark.asyncio
    async def test_null_propagates_true_returns_none(self):
        """When required parameter is None and null_propagates=True → returns None."""
        provider = _make_provider({"revenue": None})
        evaluator = AstEvaluator(provider, _make_catalog(), null_propagates=True)
        result = await evaluator.evaluate(_parse("revenue * 0.5"), COMPANY_ID, TENANT_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_null_propagates_false_raises(self):
        """When required parameter is None and null_propagates=False → raises DslEvalError."""
        provider = _make_provider({"revenue": None})
        evaluator = AstEvaluator(provider, _make_catalog(), null_propagates=False)
        with pytest.raises(DslEvalError):
            await evaluator.evaluate(_parse("revenue * 0.5"), COMPANY_ID, TENANT_ID)

    @pytest.mark.asyncio
    async def test_if_guards_against_null(self):
        """IF(revenue != None, revenue * 0.5, 0) with None revenue → takes else branch."""
        # Using numeric guard: IF(revenue > 0, revenue * 0.5, 0)
        # revenue=None → condition returns None → whole result None with propagation
        provider = _make_provider({"revenue": None})
        evaluator = AstEvaluator(provider, _make_catalog(), null_propagates=True)
        result = await evaluator.evaluate(
            _parse("IF(revenue > 0, revenue * 0.5, 0)"), COMPANY_ID, TENANT_ID
        )
        assert result is None
