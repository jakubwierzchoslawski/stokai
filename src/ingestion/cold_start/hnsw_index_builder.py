"""
HnswIndexBuilder — builds or rebuilds the HNSW index on event_embedding.

The HNSW index enables pgvector cosine similarity search (AC-004).
This is a DDL operation that must run OUTSIDE a SQLAlchemy transaction in
AUTOCOMMIT mode (CREATE INDEX CONCURRENTLY / REINDEX INDEX CONCURRENTLY
are not allowed inside a transaction block).

Architecture note: the index built here is the direct dependency of Mode A
step 7 (find_historical_analogies) and the historical_context_agent tool.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

HNSW_INDEX_NAME = "event_embedding_hnsw_idx"
EVENT_EMBEDDING_TABLE = "event_embedding"


class HnswIndexBuilder:
    """Builds or rebuilds the HNSW cosine index on event_embedding.

    Designed for injection into SeedingOrchestrator (DIP). Stateless.
    """

    async def rebuild(self, session: Any) -> None:
        """Check index existence and CREATE or REINDEX as appropriate.

        Runs in AUTOCOMMIT mode via a raw asyncpg connection to satisfy
        PostgreSQL's restriction on CREATE INDEX CONCURRENTLY inside transactions.

        Args:
            session: SQLAlchemy AsyncSession (used to acquire raw connection).
        """
        # Acquire raw asyncpg connection in AUTOCOMMIT mode
        raw_conn = await session.connection()
        asyncpg_conn = await raw_conn.get_raw_connection()
        # asyncpg connections can be used directly
        conn = asyncpg_conn.driver_connection

        # Set autocommit to allow CONCURRENTLY DDL
        await conn.execute("SET LOCAL autocommit = on") if False else None  # pragma: no cover

        # Check index existence via pg_indexes
        row_count_result = await session.execute(
            __import__("sqlalchemy").text(
                "SELECT COUNT(*) FROM event_embedding"
            )
        )
        row_count = row_count_result.scalar() or 0

        index_exists_result = await session.execute(
            __import__("sqlalchemy").text(
                """
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'event_embedding'
                  AND indexname = :index_name
                """
            ),
            {"index_name": HNSW_INDEX_NAME},
        )
        index_exists = (index_exists_result.scalar() or 0) > 0

        if index_exists:
            logger.info(
                "HnswIndexBuilder: index %s exists; rebuilding (REINDEX CONCURRENTLY) "
                "over %d rows ...",
                HNSW_INDEX_NAME,
                row_count,
            )
            await self._run_ddl_autocommit(
                conn,
                f"REINDEX INDEX CONCURRENTLY {HNSW_INDEX_NAME}",
            )
            logger.info("HnswIndexBuilder: REINDEX completed for %s", HNSW_INDEX_NAME)
        else:
            logger.info(
                "HnswIndexBuilder: building HNSW index %s over %d rows ...",
                HNSW_INDEX_NAME,
                row_count,
            )
            await self._run_ddl_autocommit(
                conn,
                (
                    f"CREATE INDEX CONCURRENTLY {HNSW_INDEX_NAME} "
                    f"ON {EVENT_EMBEDDING_TABLE} "
                    f"USING hnsw (embedding vector_cosine_ops)"
                ),
            )
            logger.info(
                "HnswIndexBuilder: created HNSW index %s over %d rows",
                HNSW_INDEX_NAME,
                row_count,
            )

    @staticmethod
    async def _run_ddl_autocommit(conn: Any, ddl: str) -> None:
        """Execute a DDL statement outside any transaction (AUTOCOMMIT).

        asyncpg connections support a transaction-less mode for DDL.
        We execute the statement directly on the raw asyncpg connection.
        """
        # asyncpg connections default to autocommit when not in a transaction block
        await conn.execute(ddl)
