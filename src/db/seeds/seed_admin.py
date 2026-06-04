"""
db.seeds.seed_admin — CLI script to create the initial admin user.

Usage:
    python -m src.db.seeds.seed_admin

Required environment variables:
    SEED_ADMIN_EMAIL    — email address for the admin user
    SEED_ADMIN_PASSWORD — plaintext password (must be >= 12 characters); never logged
    SEED_TENANT_ID      — UUID of the tenant the admin belongs to

The script is idempotent: if the email already exists for the given tenant,
it prints a notice and exits with code 0.

Security:
  - Password is hashed with bcrypt at BCRYPT_ROUNDS before any DB write.
  - Plaintext password and its hash are never printed, logged, or echoed.
"""
import asyncio
import os
import sys
import uuid

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import get_settings
from src.storage.models.user import Base, User, UserRole

_MIN_PASSWORD_LENGTH = 12


def _require_env(name: str) -> str:
    """Return the value of an environment variable or exit with a clear error."""
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"ERROR: Required environment variable '{name}' is not set or empty.", file=sys.stderr)
        sys.exit(1)
    return value


async def _seed(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    email: str,
    password_hash: str,
) -> None:
    """Insert admin user if not already present (idempotent)."""
    stmt = select(User).where(User.email == email, User.tenant_id == tenant_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        print(f"Admin user already exists, skipping.")
        return

    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=password_hash,
        role=UserRole.admin,
    )
    session.add(user)
    await session.commit()
    print(f"Admin user created: {email} (tenant: {tenant_id})")


async def main() -> None:
    email = _require_env("SEED_ADMIN_EMAIL")
    raw_password = _require_env("SEED_ADMIN_PASSWORD")
    tenant_id_str = _require_env("SEED_TENANT_ID")

    if len(raw_password) < _MIN_PASSWORD_LENGTH:
        print(
            f"ERROR: SEED_ADMIN_PASSWORD must be at least {_MIN_PASSWORD_LENGTH} characters.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        tenant_id = uuid.UUID(tenant_id_str)
    except ValueError:
        print("ERROR: SEED_TENANT_ID must be a valid UUID.", file=sys.stderr)
        sys.exit(1)

    settings = get_settings()

    crypt_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=settings.BCRYPT_ROUNDS,
    )
    # Hash in a thread executor to keep event loop unblocked (bcrypt is CPU-bound)
    loop = asyncio.get_event_loop()
    password_hash: str = await loop.run_in_executor(None, crypt_context.hash, raw_password)
    # raw_password is no longer referenced after this point; password_hash is never printed.

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        await _seed(
            session=session,
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
