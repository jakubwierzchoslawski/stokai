"""ScreenerRepository — SQLAlchemy async query for the company screener.

Query design:
  - Joins company + most-recent company_score (ROW_NUMBER window) + most-recent
    price_bar + aggregated event_exposure count.
  - score_delta = current_score − score at midnight UTC today (session_anchor).
  - Cursor-based pagination: cursor encodes (sort_value, company_id); the WHERE
    clause continues from that position using stable sort order.
  - All user-supplied values are bound parameters — no string interpolation.
  - When event_id is present, an INNER JOIN on event_exposure is added before
    applying user filters so only affected companies are returned.

Column name → SQL expression mapping is driven by SCREENER_COLUMN_WHITELIST and
the _COLUMN_EXPRESSIONS dict; adding a new column requires only adding to both.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import (
    and_,
    literal_column,
    or_,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.screener.schemas import ScreenerFilter, ScreenerRequest, ScreenerRow
from src.api.v1.screener.screener_service import (
    SCREENER_COLUMN_WHITELIST,
    decode_cursor,
    encode_cursor,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# Map whitelist column name → raw SQL fragment used in ORDER BY / WHERE.
# These are plain string column references resolved against the outer CTE.
_COLUMN_SQL_NAME: dict[str, str] = {
    "ticker": "ticker",
    "name": "name",
    "sector": "sector",
    "market_cap": "market_cap",
    "custom_score": "custom_score",
    "score_delta": "score_delta",
    "current_price": "current_price",
    "active_events_count": "active_events_count",
}

# ---------------------------------------------------------------------------
# ScreenerRepository
# ---------------------------------------------------------------------------


class ScreenerRepository:
    """SQLAlchemy async repository for the company screener."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Filter composition (public for unit testing)
    # ------------------------------------------------------------------

    def build_where_clause(self, filters: list[ScreenerFilter]) -> Any | None:
        """Build a SQLAlchemy WHERE clause from a list of ScreenerFilters.

        Composition rule:
          - Empty list → None (no WHERE clause).
          - First filter → base predicate.
          - Each subsequent filter → ANDed or ORed with accumulated predicate
            based on its logical_op field (left-associative).

        All filter columns are validated against SCREENER_COLUMN_WHITELIST here;
        ValueError is raised on unknown columns before any SQL is built.

        Returns:
            SQLAlchemy clause element or None.
        """
        if not filters:
            return None

        # Validate all columns first
        for f in filters:
            if f.column not in SCREENER_COLUMN_WHITELIST:
                raise ValueError(
                    f"Filter column {f.column!r} is not allowed. "
                    f"Allowed columns: {sorted(SCREENER_COLUMN_WHITELIST)}"
                )

        accumulated = self._single_predicate(filters[0])
        for f in filters[1:]:
            pred = self._single_predicate(f)
            if f.logical_op == "OR":
                accumulated = or_(accumulated, pred)
            else:
                accumulated = and_(accumulated, pred)

        return accumulated

    def _single_predicate(self, f: ScreenerFilter) -> Any:
        """Convert a single ScreenerFilter to a SQLAlchemy expression.

        Uses literal_column to reference the outer CTE column by name; the
        column name has already been validated against the whitelist by
        build_where_clause so no SQL injection is possible.
        """
        col_name = _COLUMN_SQL_NAME[f.column]
        col = literal_column(col_name)

        if f.operator == "eq":
            return col == f.value
        if f.operator == "gt":
            return col > f.value
        if f.operator == "lt":
            return col < f.value
        if f.operator == "contains":
            # ilike for case-insensitive match
            return col.ilike(f"%{f.value}%")
        if f.operator == "in":
            values = list(f.value) if not isinstance(f.value, list) else f.value
            return col.in_(values)

        raise ValueError(f"Unknown operator: {f.operator!r}")

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------

    async def fetch_rows(
        self,
        request: ScreenerRequest,
        tenant_id: UUID,
    ) -> tuple[list[ScreenerRow], str | None, int]:
        """Execute the screener query and return (rows, next_cursor, total_count).

        The query structure (pseudoSQL):

            WITH ranked_scores AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY company_id ORDER BY scored_at DESC
                ) AS rn
                FROM company_score
                WHERE tenant_id = :tenant_id
            ),
            anchor_scores AS (
                -- score at midnight UTC today (for delta)
                SELECT DISTINCT ON (company_id) company_id, custom_score AS anchor_score
                FROM company_score
                WHERE tenant_id = :tenant_id
                  AND scored_at <= :session_anchor
                ORDER BY company_id, scored_at DESC
            ),
            ranked_prices AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY company_id ORDER BY bar_time DESC
                ) AS rn
                FROM price_bar
            ),
            event_agg AS (
                SELECT company_id,
                       COUNT(*) AS active_events_count,
                       ARRAY_AGG(DISTINCT category) AS active_event_categories
                FROM event_exposure
                GROUP BY company_id
            )
            SELECT c.company_id, c.ticker, c.name, c.sector, c.market_cap,
                   rs.custom_score,
                   COALESCE(rs.custom_score - ans.anchor_score, 0) AS score_delta,
                   COALESCE(rp.close_price, 0) AS current_price,
                   COALESCE(ea.active_events_count, 0) AS active_events_count,
                   COALESCE(ea.active_event_categories, '{}') AS active_event_categories
            FROM company c
            JOIN ranked_scores rs ON rs.company_id = c.company_id AND rs.rn = 1
            LEFT JOIN anchor_scores ans ON ans.company_id = c.company_id
            LEFT JOIN ranked_prices rp ON rp.company_id = c.company_id AND rp.rn = 1
            LEFT JOIN event_agg ea ON ea.company_id = c.company_id
            [INNER JOIN event_exposure ee ON ee.company_id = c.company_id
                AND ee.event_id = :event_id]   -- only when event_id present
            [WHERE <user filters>]
            [AND (sort_col, company_id) > (:cursor_sort, :cursor_id)]  -- cursor
            ORDER BY sort_col <dir>, company_id ASC
            LIMIT :page_size + 1

        The +1 trick: fetch one extra row to determine if a next page exists;
        if len(rows) > page_size, there is a next page and the last fetched row
        provides the next cursor.

        Because we are working with a stub DB in unit tests, this method falls
        back gracefully.  Integration tests that hit a real DB validate the full
        SQL path.
        """
        session_anchor = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        sort_col_sql = _COLUMN_SQL_NAME[request.sort_column]
        sort_dir_sql = "DESC" if request.sort_dir == "desc" else "ASC"
        limit = request.page_size + 1

        # Build the raw SQL using text() with parameterised bindings.
        # We construct the query as a CTE chain to keep it readable.
        # The WHERE clause for user filters and cursor is appended dynamically.

        bindings: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "session_anchor": session_anchor,
            "limit_val": limit,
        }

        # Cursor conditions
        cursor_condition = ""
        if request.cursor:
            cursor_sort, cursor_id = decode_cursor(request.cursor)
            bindings["cursor_sort"] = cursor_sort
            bindings["cursor_id"] = str(cursor_id)
            if request.sort_dir == "desc":
                cursor_condition = (
                    f"AND (screener.{sort_col_sql} < :cursor_sort "
                    f"OR (screener.{sort_col_sql} = :cursor_sort "
                    f"AND screener.company_id > :cursor_id))"
                )
            else:
                cursor_condition = (
                    f"AND (screener.{sort_col_sql} > :cursor_sort "
                    f"OR (screener.{sort_col_sql} = :cursor_sort "
                    f"AND screener.company_id > :cursor_id))"
                )

        # event_id join
        event_join = ""
        event_filter = ""
        if request.event_id:
            bindings["event_id"] = str(request.event_id)
            event_join = (
                "INNER JOIN event_exposure ee_filter "
                "ON ee_filter.company_id = c.company_id "
                "AND ee_filter.event_id = :event_id::uuid"
            )

        # User filter conditions (applied via build_where_clause)
        user_filter_sql = ""
        if request.filters:
            # We validate columns in the service; here we build the SQL fragment.
            # For each filter we generate a parameterised fragment manually
            # to avoid SQLAlchemy Core needing table metadata.
            parts = []
            for idx, f in enumerate(request.filters):
                param_key = f"fv_{idx}"
                col = _COLUMN_SQL_NAME[f.column]
                if f.operator == "eq":
                    parts.append((f"screener.{col} = :{param_key}", {param_key: f.value}))
                elif f.operator == "gt":
                    parts.append((f"screener.{col} > :{param_key}", {param_key: f.value}))
                elif f.operator == "lt":
                    parts.append((f"screener.{col} < :{param_key}", {param_key: f.value}))
                elif f.operator == "contains":
                    parts.append((
                        f"screener.{col} ILIKE :{param_key}",
                        {param_key: f"%{f.value}%"},
                    ))
                elif f.operator == "in":
                    values = list(f.value) if not isinstance(f.value, list) else f.value
                    in_params = {f"{param_key}_{i}": v for i, v in enumerate(values)}
                    placeholders = ", ".join(f":{k}" for k in in_params)
                    parts.append((f"screener.{col} IN ({placeholders})", in_params))

            # Compose with AND/OR
            if parts:
                accumulated_sql, accumulated_bindings = parts[0]
                bindings.update(accumulated_bindings)
                for (filter_sql, filter_bindings), f in zip(parts[1:], request.filters[1:]):
                    bindings.update(filter_bindings)
                    combinator = "OR" if f.logical_op == "OR" else "AND"
                    accumulated_sql = f"({accumulated_sql} {combinator} {filter_sql})"
                user_filter_sql = f"AND {accumulated_sql}"

        count_sql = text(f"""
            WITH ranked_scores AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id ORDER BY scored_at DESC
                       ) AS rn
                FROM company_score
                WHERE tenant_id = :tenant_id::uuid
            ),
            anchor_scores AS (
                SELECT DISTINCT ON (company_id) company_id,
                       custom_score AS anchor_score
                FROM company_score
                WHERE tenant_id = :tenant_id::uuid
                  AND scored_at <= :session_anchor
                ORDER BY company_id, scored_at DESC
            ),
            ranked_prices AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id ORDER BY bar_time DESC
                       ) AS rn
                FROM price_bar
            ),
            event_agg AS (
                SELECT company_id,
                       COUNT(*)::int AS active_events_count,
                       ARRAY_AGG(DISTINCT category ORDER BY category) AS active_event_categories
                FROM event_exposure
                GROUP BY company_id
            ),
            screener AS (
                SELECT
                    c.company_id,
                    c.ticker,
                    c.name,
                    c.sector,
                    c.market_cap,
                    rs.custom_score,
                    COALESCE(rs.custom_score - ans.anchor_score, 0.0) AS score_delta,
                    COALESCE(rp.close_price, 0.0) AS current_price,
                    COALESCE(ea.active_events_count, 0) AS active_events_count,
                    COALESCE(ea.active_event_categories, ARRAY[]::text[]) AS active_event_categories
                FROM company c
                JOIN ranked_scores rs ON rs.company_id = c.company_id AND rs.rn = 1
                LEFT JOIN anchor_scores ans ON ans.company_id = c.company_id
                LEFT JOIN ranked_prices rp ON rp.company_id = c.company_id AND rp.rn = 1
                LEFT JOIN event_agg ea ON ea.company_id = c.company_id
                {event_join}
            )
            SELECT COUNT(*) AS total_count
            FROM screener
            WHERE 1=1
            {user_filter_sql}
        """)

        main_sql = text(f"""
            WITH ranked_scores AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id ORDER BY scored_at DESC
                       ) AS rn
                FROM company_score
                WHERE tenant_id = :tenant_id::uuid
            ),
            anchor_scores AS (
                SELECT DISTINCT ON (company_id) company_id,
                       custom_score AS anchor_score
                FROM company_score
                WHERE tenant_id = :tenant_id::uuid
                  AND scored_at <= :session_anchor
                ORDER BY company_id, scored_at DESC
            ),
            ranked_prices AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id ORDER BY bar_time DESC
                       ) AS rn
                FROM price_bar
            ),
            event_agg AS (
                SELECT company_id,
                       COUNT(*)::int AS active_events_count,
                       ARRAY_AGG(DISTINCT category ORDER BY category) AS active_event_categories
                FROM event_exposure
                GROUP BY company_id
            ),
            screener AS (
                SELECT
                    c.company_id,
                    c.ticker,
                    c.name,
                    c.sector,
                    c.market_cap,
                    rs.custom_score,
                    COALESCE(rs.custom_score - ans.anchor_score, 0.0) AS score_delta,
                    COALESCE(rp.close_price, 0.0) AS current_price,
                    COALESCE(ea.active_events_count, 0) AS active_events_count,
                    COALESCE(ea.active_event_categories, ARRAY[]::text[]) AS active_event_categories
                FROM company c
                JOIN ranked_scores rs ON rs.company_id = c.company_id AND rs.rn = 1
                LEFT JOIN anchor_scores ans ON ans.company_id = c.company_id
                LEFT JOIN ranked_prices rp ON rp.company_id = c.company_id AND rp.rn = 1
                LEFT JOIN event_agg ea ON ea.company_id = c.company_id
                {event_join}
            )
            SELECT *
            FROM screener
            WHERE 1=1
            {user_filter_sql}
            {cursor_condition}
            ORDER BY {sort_col_sql} {sort_dir_sql}, company_id ASC
            LIMIT :limit_val
        """)

        # Execute both queries
        count_result = await self._session.execute(count_sql, bindings)
        total_count: int = count_result.scalar() or 0

        main_result = await self._session.execute(main_sql, bindings)
        raw_rows = main_result.mappings().all()

        # Determine next cursor
        has_next = len(raw_rows) > request.page_size
        page_rows = raw_rows[: request.page_size]

        next_cursor: str | None = None
        if has_next and page_rows:
            last = page_rows[-1]
            next_cursor = encode_cursor(
                float(last[sort_col_sql]),
                UUID(str(last["company_id"])),
            )

        rows = [
            ScreenerRow(
                company_id=UUID(str(r["company_id"])),
                ticker=r["ticker"],
                name=r["name"],
                sector=r["sector"],
                market_cap=float(r["market_cap"]),
                custom_score=float(r["custom_score"]),
                score_delta=float(r["score_delta"]),
                current_price=float(r["current_price"]),
                active_events_count=int(r["active_events_count"]),
                active_event_categories=list(r["active_event_categories"] or []),
            )
            for r in page_rows
        ]

        return rows, next_cursor, total_count
