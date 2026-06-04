"""
storage.repositories.base — TenantScopedRepository abstract base class.

All repository classes that access tenant-partitioned data must inherit from
TenantScopedRepository and use the _scoped_select / _scoped_update /
_scoped_delete helpers instead of constructing raw SQLAlchemy statements.

Design note — geo_event exception
-----------------------------------
The geo_event table stores globally-shared events (tenant_id IS NULL) alongside
tenant-specific events. Queries against geo_event must NOT use TenantScopedRepository
directly; instead they should apply their own (tenant_id IS NULL OR tenant_id = :tid)
filter so that global events are visible to all tenants while tenant-scoped events
remain isolated.
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.sql.dml import Delete, Update
from sqlalchemy.sql.selectable import Select


class TenantIdMissingError(Exception):
    """Raised when a repository method is called without a tenant_id.

    Every query that touches tenant-partitioned data must carry a non-None
    tenant_id. Raising this error is a structural guard that prevents accidental
    cross-tenant data access at the Python layer — before any SQL is executed.
    """


class TenantScopedRepository:
    """Abstract base class for SQLAlchemy 2.0 async repositories.

    Subclasses receive three helper methods that build SQLAlchemy
    Select / Update / Delete statements with a pre-attached
    ``WHERE <model>.tenant_id = :tenant_id`` clause.

    Usage in a subclass::

        class MyRepository(TenantScopedRepository):
            def __init__(self, session: AsyncSession) -> None:
                self._session = session

            async def get_by_name(self, name: str, tenant_id: uuid.UUID):
                stmt = self._scoped_select(MyModel, tenant_id).where(
                    MyModel.name == name
                )
                result = await self._session.execute(stmt)
                return result.scalar_one_or_none()
    """

    # ── Scoped statement builders ─────────────────────────────────────────────

    def _scoped_select(self, model: type, tenant_id: uuid.UUID | None) -> Select:
        """Return a SELECT statement pre-filtered by tenant_id.

        Args:
            model: The SQLAlchemy ORM model class (must have a tenant_id column).
            tenant_id: The UUID of the requesting tenant. Must not be None.

        Raises:
            TenantIdMissingError: If tenant_id is None.

        Returns:
            A SQLAlchemy Select object with WHERE model.tenant_id = :tenant_id
            already attached. Chain additional .where() clauses as needed.
        """
        self._guard_tenant_id(tenant_id)
        return select(model).where(model.tenant_id == tenant_id)

    def _scoped_update(self, model: type, tenant_id: uuid.UUID | None) -> Update:
        """Return an UPDATE statement pre-filtered by tenant_id.

        Args:
            model: The SQLAlchemy ORM model class (must have a tenant_id column).
            tenant_id: The UUID of the requesting tenant. Must not be None.

        Raises:
            TenantIdMissingError: If tenant_id is None.

        Returns:
            A SQLAlchemy Update object with WHERE model.tenant_id = :tenant_id
            already attached. Chain .where() and .values() as needed.
        """
        self._guard_tenant_id(tenant_id)
        return update(model).where(model.tenant_id == tenant_id)

    def _scoped_delete(self, model: type, tenant_id: uuid.UUID | None) -> Delete:
        """Return a DELETE statement pre-filtered by tenant_id.

        Args:
            model: The SQLAlchemy ORM model class (must have a tenant_id column).
            tenant_id: The UUID of the requesting tenant. Must not be None.

        Raises:
            TenantIdMissingError: If tenant_id is None.

        Returns:
            A SQLAlchemy Delete object with WHERE model.tenant_id = :tenant_id
            already attached. Chain additional .where() clauses as needed.
        """
        self._guard_tenant_id(tenant_id)
        return delete(model).where(model.tenant_id == tenant_id)

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _guard_tenant_id(tenant_id: uuid.UUID | None) -> None:
        """Raise TenantIdMissingError if tenant_id is None."""
        if tenant_id is None:
            raise TenantIdMissingError(
                "tenant_id must not be None. Every repository query must be "
                "scoped to a specific tenant to prevent cross-tenant data access."
            )
