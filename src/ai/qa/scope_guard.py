"""
ai.qa.scope_guard — QAScopeGuard: portfolio scope enforcement for Q&A.

PLAN-F-027 TASK-002

Extracts ticker symbols from the user's question using a regex (no LLM).
Checks each ticker against the user's portfolio+watchlist (via injected tool).
If a ticker is found in the question but NOT in the portfolio/watchlist,
the question is out-of-scope.

If no specific company/ticker is referenced → always in_scope=True.

Design decisions:
- Pure regex extraction: fast, deterministic, no LLM cost.
- Portfolio lookup via an injected async callable (dependency inversion).
- ScopeCheckResult is a plain Pydantic model — no DB access inside.
"""
from __future__ import annotations

import re
from typing import Awaitable, Callable
from uuid import UUID

from pydantic import BaseModel


# Regex: 1-5 uppercase letters, not preceded/followed by alphanumeric.
# Captures common US ticker formats: AAPL, TSLA, GOOGL, MSFT, BRK, etc.
_TICKER_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,5})(?![A-Z0-9])")

# Words that look like tickers but are common English words — exclude them
# to reduce false positives. Extend as needed.
_COMMON_WORDS = frozenset(
    {
        "I", "A", "AN", "THE", "AND", "OR", "NOT", "IN", "ON", "AT",
        "TO", "OF", "FOR", "IS", "IT", "BE", "DO", "GO", "NO", "SO",
        "US", "IF", "BY", "UP", "AS", "MY", "WE", "HE", "SHE", "ARE",
        "HAS", "HAD", "WAS", "CAN", "DID", "GET", "GOT", "PUT", "OUT",
        "ALL", "ANY", "BUT", "HOW", "NEW", "NOW", "OFF", "OLD", "OUR",
        "OWN", "SAY", "SEE", "SET", "TWO", "WAY", "WHO", "WHY", "YOU",
        "YET", "LOT", "ONE", "TEN", "TOP", "TOO", "USE", "MAY", "BIG",
        "BUY", "DAY", "END", "FEW", "HAD", "HIM", "HIS", "ITS", "LET",
        "LOW", "MAN", "MEN", "MUCH", "NEXT", "ONLY", "OPEN", "OVER",
        "PART", "PAST", "RATE", "REAL", "RISK", "SAFE", "SAME", "SIDE",
        "SOME", "SUCH", "SURE", "THAN", "THEM", "THEN", "THEY", "THIS",
        "THUS", "TILL", "TOLD", "UPON", "VERY", "WANT", "WELL", "WERE",
        "WHAT", "WHEN", "WITH", "WORK", "YEAR", "YOUR",
        # Finance-domain common words that are not tickers
        "ETF", "IPO", "CEO", "CFO", "COO", "CTO", "SEC", "GDP", "CPI",
        "EPS", "P/E", "PE", "ROE", "ROI", "NAV", "AUM", "FED", "ECB",
        "IMF", "NYSE", "NASDAQ", "DJIA", "QE", "QT", "YOY", "MOM",
        "CAGR", "DCF", "EBITDA", "WACC", "FCF", "TTM", "LTM",
    }
)


class ScopeCheckResult(BaseModel):
    """Result of the portfolio scope guard check."""

    in_scope: bool
    out_of_scope_tickers: list[str]
    suggestion: str | None


# Type alias for the portfolio lookup callable
PortfolioLookupFn = Callable[[UUID, list[str]], Awaitable[list[str]]]


def extract_tickers(text: str) -> list[str]:
    """Extract potential ticker symbols from text using regex.

    Returns a de-duplicated list of uppercase tokens that match the ticker
    pattern and are not common English words.

    Args:
        text: User question or any text string.

    Returns:
        List of candidate ticker symbols (may include false positives).
    """
    candidates = _TICKER_RE.findall(text.upper())
    seen: set[str] = set()
    result: list[str] = []
    for tok in candidates:
        if tok not in _COMMON_WORDS and tok not in seen:
            seen.add(tok)
            result.append(tok)
    return result


class QAScopeGuard:
    """Portfolio scope guard for Q&A sessions.

    Checks that every ticker mentioned in a question belongs to the user's
    portfolio or watchlist. Uses a regex extraction step (no LLM) followed
    by an async lookup against the portfolio tool.

    Args:
        portfolio_lookup_fn:
            Async callable (tenant_id, tickers) -> list[str] of tickers that
            ARE in the portfolio/watchlist. Injected for testability.
    """

    def __init__(self, portfolio_lookup_fn: PortfolioLookupFn) -> None:
        self._lookup = portfolio_lookup_fn

    async def check(
        self, question: str, tenant_id: UUID
    ) -> ScopeCheckResult:
        """Check whether the question is within portfolio scope.

        Rules:
          - No tickers extracted → always in_scope=True (general question).
          - All tickers found in portfolio/watchlist → in_scope=True.
          - At least one ticker NOT in portfolio/watchlist → in_scope=False.

        Args:
            question: The user's natural language question.
            tenant_id: The tenant whose portfolio to check against.

        Returns:
            ScopeCheckResult with in_scope, out_of_scope_tickers, suggestion.
        """
        tickers = extract_tickers(question)

        if not tickers:
            # No specific company referenced → always in scope
            return ScopeCheckResult(
                in_scope=True,
                out_of_scope_tickers=[],
                suggestion=None,
            )

        # Ask the portfolio lookup which tickers are in scope
        in_portfolio: list[str] = await self._lookup(tenant_id, tickers)
        in_portfolio_set = set(in_portfolio)

        out_of_scope = [t for t in tickers if t not in in_portfolio_set]

        if not out_of_scope:
            return ScopeCheckResult(
                in_scope=True,
                out_of_scope_tickers=[],
                suggestion=None,
            )

        ticker_list = ", ".join(out_of_scope)
        suggestion = (
            f"The ticker(s) {ticker_list} are not in your portfolio or watchlist. "
            f"Add them to your watchlist to ask questions about these companies."
        )
        return ScopeCheckResult(
            in_scope=False,
            out_of_scope_tickers=out_of_scope,
            suggestion=suggestion,
        )
