"""ScreenerService — business logic for the company screener.

Responsibilities:
  1. Validate filter columns against SCREENER_COLUMN_WHITELIST.
  2. Delegate the parameterised query to ScreenerRepository.
  3. Expose cursor encode/decode as module-level helpers.

SCREENER_COLUMN_WHITELIST is the single source of truth shared by the service
(validation) and repository (SQL column mapping).  The TypeScript frontend
mirrors this list in screenerTypes.ts; keep them in sync when adding columns.
"""
from __future__ import annotations

import base64
import logging
from uuid import UUID

from src.api.v1.screener.schemas import ScreenerFilter, ScreenerRequest, ScreenerRow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column whitelist — single source of truth (backend).
# Mirror this set in src/frontend/features/screener/screenerTypes.ts.
# ---------------------------------------------------------------------------

SCREENER_COLUMN_WHITELIST: frozenset[str] = frozenset({
    "ticker",
    "name",
    "sector",
    "market_cap",
    "custom_score",
    "score_delta",
    "current_price",
    "active_events_count",
})

# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------

_CURSOR_SEP = ":"


def encode_cursor(sort_value: float, company_id: UUID) -> str:
    """Encode a cursor token from (sort_value, company_id).

    Format: base64(repr(sort_value) + ":" + str(company_id))
    The token is opaque to clients.
    """
    raw = f"{repr(sort_value)}{_CURSOR_SEP}{company_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[float, UUID]:
    """Decode a cursor token back to (sort_value, company_id).

    Raises ValueError if the cursor is malformed.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        # Split on the *first* colon only — UUID contains hyphens not colons so
        # the UUID portion is everything after the first colon.
        first_sep = raw.index(_CURSOR_SEP)
        sort_raw = raw[:first_sep]
        id_raw = raw[first_sep + 1:]
        return float(sort_raw), UUID(id_raw)
    except Exception as exc:
        raise ValueError(f"Malformed cursor: {cursor!r}") from exc


# ---------------------------------------------------------------------------
# ScreenerService
# ---------------------------------------------------------------------------


class ScreenerService:
    """Orchestrates screener validation and repository delegation."""

    def __init__(self, repository) -> None:  # repository: ScreenerRepository
        self._repo = repository

    # ------------------------------------------------------------------
    # Static / class-level validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def validate_filters(filters: list[ScreenerFilter]) -> None:
        """Validate that all filter columns are in SCREENER_COLUMN_WHITELIST.

        Raises:
            ValueError: If any filter references an unknown column.  The error
                message names the offending column so the caller can surface it
                as a 422 detail.
        """
        for f in filters:
            if f.column not in SCREENER_COLUMN_WHITELIST:
                raise ValueError(
                    f"Filter column {f.column!r} is not allowed. "
                    f"Allowed columns: {sorted(SCREENER_COLUMN_WHITELIST)}"
                )

    @staticmethod
    def validate_sort_column(sort_column: str) -> None:
        """Validate that the sort column is whitelisted.

        Raises:
            ValueError: If sort_column is not in SCREENER_COLUMN_WHITELIST.
        """
        if sort_column not in SCREENER_COLUMN_WHITELIST:
            raise ValueError(
                f"Sort column {sort_column!r} is not allowed. "
                f"Allowed columns: {sorted(SCREENER_COLUMN_WHITELIST)}"
            )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        request: ScreenerRequest,
        tenant_id: UUID,
    ) -> tuple[list[ScreenerRow], str | None, int]:
        """Execute the screener query and return (rows, next_cursor, total_count).

        Validates filters and sort column, then delegates to the repository.

        Raises:
            ValueError: On unknown filter column or sort column (→ 422 in router).
        """
        self.validate_filters(request.filters)
        self.validate_sort_column(request.sort_column)
        return await self._repo.fetch_rows(request, tenant_id)
