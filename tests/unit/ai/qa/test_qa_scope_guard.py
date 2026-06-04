"""
Unit tests for QAScopeGuard (PLAN-F-027 TASK-002).

Scope guard uses regex ticker extraction (no LLM).
Portfolio lookup is injected as an async callable (mockable).

Tests:
  - portfolio ticker → in_scope=True
  - no ticker reference → in_scope=True
  - unknown ticker → in_scope=False with suggestion naming the ticker
  - uses tenant_id for lookup
  - suggestion names the out-of-scope ticker
"""
from __future__ import annotations

import uuid

import pytest

from src.ai.qa.scope_guard import QAScopeGuard, ScopeCheckResult, extract_tickers


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


# ── extract_tickers() unit tests ──────────────────────────────────────────────


class TestExtractTickers:
    """Unit tests for the regex ticker extraction helper."""

    def test_extracts_known_ticker(self):
        assert "AAPL" in extract_tickers("What is my AAPL exposure?")

    def test_extracts_multiple_tickers(self):
        tickers = extract_tickers("Compare AAPL and MSFT performance.")
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_no_tickers_in_general_question(self):
        tickers = extract_tickers("What is my overall portfolio performance?")
        # 'my' filtered by common words; no tickers
        assert tickers == []

    def test_ignores_common_english_words(self):
        tickers = extract_tickers("Is the market doing well today?")
        assert "IS" not in tickers
        assert "THE" not in tickers

    def test_extracts_five_letter_ticker(self):
        tickers = extract_tickers("Tell me about GOOGL revenue trends.")
        assert "GOOGL" in tickers

    def test_does_not_extract_lowercase(self):
        tickers = extract_tickers("What about apple stock?")
        # 'apple' is lowercase, won't match uppercase-only regex
        assert "APPLE" not in tickers


# ── QAScopeGuard tests ─────────────────────────────────────────────────────────


class TestQAScopeGuardPortfolioTicker:
    """Portfolio ticker → in_scope=True."""

    @pytest.mark.asyncio
    async def test_portfolio_ticker_is_in_scope(self, tenant_id):
        """A ticker that IS in portfolio returns in_scope=True."""

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            # AAPL is in portfolio
            return [t for t in tickers if t == "AAPL"]

        guard = QAScopeGuard(lookup)
        result = await guard.check("What is my AAPL exposure?", tenant_id)

        assert result.in_scope is True
        assert result.out_of_scope_tickers == []
        assert result.suggestion is None

    @pytest.mark.asyncio
    async def test_multiple_portfolio_tickers_all_in_scope(self, tenant_id):
        """Multiple tickers, all in portfolio → in_scope=True."""

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            portfolio = {"AAPL", "MSFT"}
            return [t for t in tickers if t in portfolio]

        guard = QAScopeGuard(lookup)
        result = await guard.check("Compare AAPL and MSFT.", tenant_id)

        assert result.in_scope is True
        assert result.out_of_scope_tickers == []


class TestQAScopeGuardNoTicker:
    """No ticker reference → always in_scope=True."""

    @pytest.mark.asyncio
    async def test_no_ticker_always_in_scope(self, tenant_id):
        """General question with no tickers is always in scope."""
        called = []

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            called.append(tickers)
            return []

        guard = QAScopeGuard(lookup)
        result = await guard.check("What is my overall portfolio performance?", tenant_id)

        assert result.in_scope is True
        assert result.out_of_scope_tickers == []
        assert result.suggestion is None
        # lookup should NOT be called if no tickers extracted
        assert called == []

    @pytest.mark.asyncio
    async def test_empty_question_in_scope(self, tenant_id):
        """Empty string → in_scope=True."""

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            return []

        guard = QAScopeGuard(lookup)
        result = await guard.check("", tenant_id)

        assert result.in_scope is True


class TestQAScopeGuardUnknownTicker:
    """Unknown ticker → in_scope=False with suggestion naming the ticker."""

    @pytest.mark.asyncio
    async def test_unknown_ticker_returns_out_of_scope(self, tenant_id):
        """Ticker not in portfolio/watchlist → in_scope=False."""

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            # NVDA is NOT in portfolio
            return []

        guard = QAScopeGuard(lookup)
        result = await guard.check("Tell me about NVDA earnings.", tenant_id)

        assert result.in_scope is False
        assert "NVDA" in result.out_of_scope_tickers

    @pytest.mark.asyncio
    async def test_suggestion_names_the_out_of_scope_ticker(self, tenant_id):
        """Suggestion text explicitly names the unknown ticker."""

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            return []

        guard = QAScopeGuard(lookup)
        result = await guard.check("What is TSLA worth?", tenant_id)

        assert result.suggestion is not None
        assert "TSLA" in result.suggestion

    @pytest.mark.asyncio
    async def test_mixed_tickers_partial_out_of_scope(self, tenant_id):
        """AAPL in portfolio, NVDA not → in_scope=False, NVDA in out_of_scope_tickers."""

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            return [t for t in tickers if t == "AAPL"]

        guard = QAScopeGuard(lookup)
        result = await guard.check("Compare AAPL and NVDA.", tenant_id)

        assert result.in_scope is False
        assert "NVDA" in result.out_of_scope_tickers
        assert "AAPL" not in result.out_of_scope_tickers


class TestQAScopeGuardUsesTenantId:
    """Scope guard passes tenant_id to the portfolio lookup callable."""

    @pytest.mark.asyncio
    async def test_tenant_id_passed_to_lookup(self, tenant_id):
        """The portfolio lookup receives the correct tenant_id."""
        received_tenant_ids: list[uuid.UUID] = []

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            received_tenant_ids.append(tid)
            return tickers  # all in scope

        guard = QAScopeGuard(lookup)
        await guard.check("How is AAPL doing?", tenant_id)

        assert received_tenant_ids == [tenant_id]

    @pytest.mark.asyncio
    async def test_different_tenants_get_separate_lookup_calls(self):
        """Each call uses its own tenant_id (no cross-tenant caching)."""
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        received: list[uuid.UUID] = []

        async def lookup(tid: uuid.UUID, tickers: list[str]) -> list[str]:
            received.append(tid)
            return tickers

        guard = QAScopeGuard(lookup)
        await guard.check("AAPL exposure?", tenant_a)
        await guard.check("AAPL exposure?", tenant_b)

        assert tenant_a in received
        assert tenant_b in received
        assert received[0] != received[1]
