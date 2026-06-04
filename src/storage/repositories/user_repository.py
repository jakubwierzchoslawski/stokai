"""
storage.repositories.user_repository — UserRepository for the user table.

All queries include tenant_id in the WHERE clause via TenantScopedRepository
(REQ-N-006 / Principle 3). No business logic lives here — only SQL via
SQLAlchemy 2.0 async ORM.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.user import User, UserRole
from src.storage.repositories.base import TenantScopedRepository


class UserRepository(TenantScopedRepository):
    """Repository for user entity persistence.

    Inherits TenantScopedRepository to structurally enforce tenant_id in every
    query. All public methods accept tenant_id and delegate scoping to the base
    class helpers — no cross-tenant data leakage is possible at the repository layer.

    Injected via constructor (DIP) — no hard-coded session creation here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def getByEmail(self, email: str, tenant_id: uuid.UUID) -> User | None:
        """Retrieve a user by email within the specified tenant.

        Returns None if no matching user exists.
        tenant_id is enforced via _scoped_select (IDOR prevention).
        """
        stmt = self._scoped_select(User, tenant_id).where(
            User.email == email,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def getById(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> User | None:
        """Retrieve a user by primary key within the specified tenant.

        Returns None if the user does not exist or belongs to a different tenant.
        """
        stmt = self._scoped_select(User, tenant_id).where(
            User.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        tenant_id: uuid.UUID,
        email: str,
        password_hash: str,
        role: UserRole,
    ) -> User:
        """Insert a new user row and return the persisted entity.

        password_hash must already be a bcrypt hash — never a plaintext password.
        """
        user = User(
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user
