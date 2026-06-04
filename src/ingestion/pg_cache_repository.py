"""CacheEntryRepository — SQLAlchemy 2.0 async persistent-cache layer.

Implements the PostgreSQL tier of the three-tier cache (Redis → PG → API).
All queries are parameterised — no raw SQL interpolation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLAlchemy table definition (used in migration and repository)
# ---------------------------------------------------------------------------

metadata = sa.MetaData()

cache_entry_table = sa.Table(
    "cache_entry",
    metadata,
    sa.Column("cache_key", sa.Text, primary_key=True),
    sa.Column("data_type", sa.Text, nullable=False),
    sa.Column("entity_id", sa.Text, nullable=True),
    sa.Column("params_hash", sa.Text, nullable=True),
    sa.Column("value", sa.LargeBinary, nullable=False),
    sa.Column(
        "fetched_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
)


class CacheEntryRepository:
    """Repository over the ``cache_entry`` table.

    All methods accept an injected ``AsyncSession`` — this class never creates
    its own DB connection.

    Args:
        session: An active SQLAlchemy async session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cache_key: str) -> bytes | None:
        """Return cached bytes for *cache_key*, or ``None`` if miss or expired.

        The WHERE clause enforces TTL: rows where ``expires_at`` is in the past
        are treated as misses (they remain in the table until purged, but are
        never returned).

        Args:
            cache_key: The cache key.

        Returns:
            Raw bytes if the entry exists and is not expired, else ``None``.
        """
        now = datetime.now(tz=timezone.utc)
        stmt = sa.select(cache_entry_table.c.value).where(
            sa.and_(
                cache_entry_table.c.cache_key == cache_key,
                sa.or_(
                    cache_entry_table.c.expires_at.is_(None),
                    cache_entry_table.c.expires_at > now,
                ),
            )
        )
        result = await self._session.execute(stmt)
        row = result.fetchone()
        if row is None:
            return None
        return bytes(row[0])

    async def set(
        self,
        cache_key: str,
        data_type: str,
        value: bytes,
        ttl_seconds: int | None,
    ) -> None:
        """Upsert a cache entry.

        On conflict (same ``cache_key``), updates ``value``, ``fetched_at``,
        and ``expires_at``.

        Args:
            cache_key: The cache key (primary key).
            data_type: String identifier for the data type (e.g. "price_bar").
            value: Serialised payload bytes.
            ttl_seconds: Seconds until expiry; ``None`` means infinite TTL.
        """
        now = datetime.now(tz=timezone.utc)
        expires_at: datetime | None = (
            now + timedelta(seconds=ttl_seconds) if ttl_seconds is not None else None
        )

        try:
            # PostgreSQL-specific upsert
            stmt = pg_insert(cache_entry_table).values(
                cache_key=cache_key,
                data_type=data_type,
                value=value,
                fetched_at=now,
                expires_at=expires_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["cache_key"],
                set_={
                    "value": stmt.excluded.value,
                    "fetched_at": stmt.excluded.fetched_at,
                    "expires_at": stmt.excluded.expires_at,
                },
            )
            await self._session.execute(stmt)
            await self._session.commit()
        except Exception:
            # Fall back to generic upsert for non-PostgreSQL dialects (e.g. SQLite)
            await self._session.rollback()
            await self._generic_upsert(cache_key, data_type, value, now, expires_at)

    async def _generic_upsert(
        self,
        cache_key: str,
        data_type: str,
        value: bytes,
        now: datetime,
        expires_at: datetime | None,
    ) -> None:
        """Fallback upsert for non-PostgreSQL dialects (DELETE + INSERT)."""
        delete_stmt = cache_entry_table.delete().where(
            cache_entry_table.c.cache_key == cache_key
        )
        await self._session.execute(delete_stmt)
        insert_stmt = cache_entry_table.insert().values(
            cache_key=cache_key,
            data_type=data_type,
            value=value,
            fetched_at=now,
            expires_at=expires_at,
        )
        await self._session.execute(insert_stmt)
        await self._session.commit()

    async def delete(self, cache_key: str) -> None:
        """Hard-delete a cache entry (used for event-driven invalidation).

        Args:
            cache_key: The cache key to delete.
        """
        stmt = cache_entry_table.delete().where(
            cache_entry_table.c.cache_key == cache_key
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def delete_by_prefix(self, prefix: str) -> int:
        """Bulk-delete all cache entries whose key starts with *prefix*.

        Uses a parameterised LIKE query — no string interpolation.

        Args:
            prefix: Key prefix to match (e.g. ``"company_score:"``).

        Returns:
            Number of rows deleted.
        """
        stmt = (
            cache_entry_table.delete()
            .where(cache_entry_table.c.cache_key.like(prefix + "%"))
            .returning(cache_entry_table.c.cache_key)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount if result.rowcount is not None else 0
