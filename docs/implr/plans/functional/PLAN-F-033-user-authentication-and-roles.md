---
plan_id: PLAN-F-033
slug: user-authentication-and-roles
title: User Authentication and Role-Based Access Control
linked_requirement: REQ-F-033
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-006, reason: "tenant_id isolation must be enforced on every user and refresh_token query" }
dependencies: []
brainstorm_decisions:
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-033 — User Authentication and Role-Based Access Control

## Linked Requirement
**REQ-F-033** — User Authentication and Role-Based Access Control
Status: approved | Jira: (blank)

## Objective

Implement the full authentication and authorization layer for StokAI MVP. This plan
delivers: (1) a `user` table migration with role enum and tenant_id from day one; (2) a
`refresh_token` table migration for server-side token revocation; (3) a `TokenService`
that issues and validates HS256 JWT access tokens (15-minute TTL) and refresh tokens
(7-day TTL); (4) a `UserRepository` that retrieves users by email with tenant_id
isolation; (5) a `RefreshTokenRepository` for token lifecycle management; (6) an
`AuthRouter` exposing `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, and
`POST /api/v1/auth/logout`; (7) a FastAPI dependency `get_current_user` that validates
Bearer JWTs; (8) role guard dependencies (`require_admin`, `require_operator_or_above`)
for protecting admin-panel endpoints; and (9) IP-based rate limiting on auth endpoints
via SlowAPI. Refresh tokens are stored as bcrypt-hashed values in PostgreSQL and
delivered in HttpOnly cookies. Passwords are hashed with passlib bcrypt at cost factor
≥ 12. No plaintext credentials ever touch logs, responses, or error messages.

## Architecture Context

This plan touches three backend modules (Architecture §5):

- **`api`** — new `auth` sub-router registered under `/api/v1/auth`; `get_current_user`
  and role-guard FastAPI dependencies; rate-limiting middleware via SlowAPI. The `api`
  module is the entry layer only; no business logic lives here.
- **`storage`** — two new repositories (`UserRepository`, `RefreshTokenRepository`) using
  the SQLAlchemy 2.0 async ORM. Repositories are the only layer that writes SQL.
- **Alembic migrations** — two new migration scripts: one for `user` + `user_role` enum,
  one for `refresh_token`.

Architecture decision D2 (§3, §12.1) mandates: JWT access + refresh tokens, bcrypt cost
≥ 12, role field from day one, HttpOnly cookie for refresh tokens, authentication required
by default, and OAuth2 deferred to post-MVP.

Architecture principle 3 (§2) and §12.3 require every user-data table to carry
`tenant_id`. REQ-N-006 enforces tenant_id in the WHERE clause of every query.

The `TokenService` is introduced as a new internal service (not a repository, not a
controller) to keep JWT logic isolated per SRP. It belongs at
`src/api/auth/token_service.py` since it services the `api` entry layer and has no
persistence concerns of its own.

Layering rule (§5): `AuthRouter` → `AuthService` → (`UserRepository`, `RefreshTokenRepository`, `TokenService`) → Database.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-006 | tenant_id isolation on every DB query — no cross-tenant data leakage | `UserRepository.get_by_email` and `RefreshTokenRepository` all accept and enforce `tenant_id` in WHERE; IDOR guard applied in `get_current_user` dependency |

## Component Design

### New Components

```
src/
  api/
    auth/
      __init__.py
      router.py              — AuthRouter: POST /login, /refresh, /logout
      dependencies.py        — get_current_user, require_admin, require_operator_or_above
      token_service.py       — TokenService: create_access_token, create_refresh_token,
                               decode_access_token, hash_refresh_token, verify_refresh_token
      schemas.py             — LoginRequest, TokenResponse, RefreshRequest Pydantic models
    middleware/
      rate_limit.py          — SlowAPI limiter instance and decorator helpers
  storage/
    repositories/
      user_repository.py     — UserRepository: get_by_email, get_by_id, create
      refresh_token_repository.py — RefreshTokenRepository: create, get_active,
                                    revoke, revoke_all_for_user
    models/
      user.py                — SQLAlchemy ORM model: User, UserRole enum
      refresh_token.py       — SQLAlchemy ORM model: RefreshToken
  db/
    migrations/
      versions/
        0001_create_user_table.py
        0002_create_refresh_token_table.py
tests/
  unit/
    auth/
      test_token_service.py
      test_auth_service.py
      test_dependencies.py
  integration/
    auth/
      test_auth_router.py
      test_user_repository.py
      test_refresh_token_repository.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/main.py` (or app factory) | Register `auth_router` under `/api/v1` prefix | Wire new router into FastAPI app |
| `src/api/main.py` | Register SlowAPI `Limiter` as middleware, attach `_rate_limit_exceeded_handler` | Enable rate limiting globally |
| `src/config/settings.py` | Add `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 15), `JWT_REFRESH_TOKEN_EXPIRE_DAYS` (default 7), `BCRYPT_ROUNDS` (default 12) | Typed env-var config; fail fast if missing |

### Interfaces and Contracts

```python
# src/storage/repositories/user_repository.py
class UserRepository:
    async def get_by_email(self, email: str, tenant_id: UUID) -> User | None: ...
    async def get_by_id(self, user_id: UUID, tenant_id: UUID) -> User | None: ...
    async def create(self, tenant_id: UUID, email: str, password_hash: str,
                     role: UserRole) -> User: ...

# src/storage/repositories/refresh_token_repository.py
class RefreshTokenRepository:
    async def create(self, user_id: UUID, tenant_id: UUID,
                     token_hash: str, expires_at: datetime) -> RefreshToken: ...
    async def get_active(self, token_id: UUID,
                         tenant_id: UUID) -> RefreshToken | None: ...
    async def revoke(self, token_id: UUID, tenant_id: UUID) -> None: ...
    async def revoke_all_for_user(self, user_id: UUID, tenant_id: UUID) -> None: ...

# src/api/auth/token_service.py
class TokenService:
    def create_access_token(self, user_id: UUID, tenant_id: UUID,
                            role: str) -> str: ...
    def create_refresh_token(self) -> tuple[UUID, str]:
        """Returns (token_id, raw_token). raw_token is shown to client once."""
    def decode_access_token(self, token: str) -> AccessTokenClaims: ...
    def hash_refresh_token(self, raw_token: str) -> str: ...
    def verify_refresh_token(self, raw_token: str, stored_hash: str) -> bool: ...

# src/api/auth/schemas.py
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int         # seconds

class AccessTokenClaims(BaseModel):
    sub: str                # user_id as str
    tenant_id: str
    role: str
    iat: int
    exp: int

# src/api/auth/dependencies.py
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User: ...

async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User: ...

async def require_operator_or_above(
    current_user: User = Depends(get_current_user),
) -> User: ...
```

## Implementation Tasks

### TASK-001: User and RefreshToken DB migrations · S/no-TDD · src/db/migrations/versions/0001_create_user_table.py,src/db/migrations/versions/0002_create_refresh_token_table.py,src/storage/models/user.py,src/storage/models/refresh_token.py

Create two Alembic migration scripts and their corresponding SQLAlchemy ORM models.

**Migration 0001** creates the `user_role` PostgreSQL enum type and the `user` table:

```sql
CREATE TYPE user_role AS ENUM ('admin', 'operator', 'end_user');

CREATE TABLE "user" (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    email           VARCHAR(320) NOT NULL,
    password_hash   VARCHAR(72) NOT NULL,       -- bcrypt max output length
    role            user_role NOT NULL,
    settings        JSONB NOT NULL DEFAULT '{}',
    scoring_profile_default UUID,
    dispatch_time   TIME NOT NULL DEFAULT '06:00',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_email_tenant UNIQUE (email, tenant_id)
);

CREATE INDEX ix_user_tenant_id ON "user" (tenant_id);
CREATE INDEX ix_user_email ON "user" (email);
```

**Migration 0002** creates the `refresh_token` table:

```sql
CREATE TABLE refresh_token (
    token_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    tenant_id   UUID NOT NULL,
    token_hash  VARCHAR(72) NOT NULL,
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX ix_refresh_token_user_id ON refresh_token (user_id);
CREATE INDEX ix_refresh_token_tenant_id ON refresh_token (tenant_id);
```

The SQLAlchemy ORM models in `src/storage/models/user.py` and `src/storage/models/refresh_token.py` mirror these schemas using `mapped_column` with `Mapped[]` type annotations (SQLAlchemy 2.0 style). `UserRole` is a Python `enum.Enum` mapped to the PG enum via `sqlalchemy.Enum`.

**AC covered**: AC-005

---

### TASK-002: Settings extension for auth configuration · XS/no-TDD · src/config/settings.py

Extend the Pydantic `Settings` model (or create it if not yet present) to include all
auth-related environment variables:

- `JWT_SECRET_KEY: str` — required, no default; startup fails if absent
- `JWT_REFRESH_SECRET_KEY: str` — required, no default
- `JWT_ALGORITHM: str = "HS256"`
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15`
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7`
- `BCRYPT_ROUNDS: int = 12`

Use `pydantic-settings` `BaseSettings` with `model_config = SettingsConfigDict(env_file=".env")`. Validate at module-import time so the process fails fast rather than at first auth request.

**AC covered**: AC-001 (enables token TTL enforcement)

---

### TASK-003: TokenService — JWT issuance and validation · M/TDD · src/api/auth/token_service.py,tests/unit/auth/test_token_service.py

Implement `TokenService` as a pure-Python class (no DB dependency) responsible for all
JWT and token-hash concerns. It depends only on `Settings`.

**Tests to write first (TDD)**:
- `test_create_access_token_returns_decodable_jwt` — decode with the same secret; verify `sub`, `tenant_id`, `role` claims are present and correct.
- `test_access_token_expires_at_configured_ttl` — `exp` claim is within 1 second of `now + ACCESS_TOKEN_EXPIRE_MINUTES * 60`.
- `test_decode_access_token_raises_on_expired` — use a token with `exp = past`; expect `TokenExpiredError`.
- `test_decode_access_token_raises_on_tampered_signature` — flip one byte; expect `InvalidTokenError`.
- `test_create_refresh_token_returns_uuid_and_raw_string` — `token_id` is a valid UUID; raw token is a non-empty string.
- `test_hash_and_verify_refresh_token_round_trip` — `verify_refresh_token(raw, hash_refresh_token(raw))` is True.
- `test_verify_refresh_token_fails_for_wrong_token` — different raw token against stored hash is False.
- `test_hash_refresh_token_uses_bcrypt_rounds` — inspect passlib context rounds == `settings.BCRYPT_ROUNDS`.

Implementation notes:
- Use `python-jose` (or `PyJWT`) for JWT encoding/decoding.
- Use `passlib[bcrypt]` with `CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS)` — shared instance for both password and refresh-token hashing.
- `create_refresh_token` generates a `secrets.token_urlsafe(32)` raw value and a UUID token_id; the raw value is hashed before storage.
- Never log the raw token or the JWT string.

**AC covered**: AC-001 (token issuance), AC-006 (bcrypt rounds enforced here for password hash too)

---

### TASK-004: UserRepository and RefreshTokenRepository · M/TDD · src/storage/repositories/user_repository.py,src/storage/repositories/refresh_token_repository.py,tests/unit/auth/test_auth_service.py,tests/integration/auth/test_user_repository.py,tests/integration/auth/test_refresh_token_repository.py

Implement both repositories against SQLAlchemy 2.0 async sessions.

**Tests to write first (TDD)**:

Unit (mock session):
- `test_user_repository_get_by_email_returns_none_when_not_found`
- `test_user_repository_get_by_email_filters_by_tenant_id` — verify SQL has `tenant_id =` predicate (inspect the compiled query or use mock assertions).
- `test_user_repository_get_by_id_filters_by_tenant_id`
- `test_refresh_token_repository_get_active_excludes_revoked` — `revoked_at IS NULL` and `expires_at > now()` in predicate.
- `test_refresh_token_repository_revoke_sets_revoked_at`
- `test_refresh_token_repository_revoke_all_for_user_updates_all_rows`

Integration (real test DB via pytest-asyncio + transaction rollback fixture):
- `test_create_and_retrieve_user_by_email`
- `test_get_user_by_email_wrong_tenant_returns_none` — insert with tenant_A, query with tenant_B; must return None.
- `test_create_refresh_token_and_get_active`
- `test_revoke_token_makes_get_active_return_none`
- `test_revoke_all_for_user_revokes_all_tokens`

Implementation notes:
- All `SELECT` statements include `WHERE tenant_id = :tenant_id` — no exceptions.
- Use `select(User).where(User.tenant_id == tenant_id, User.email == email)` syntax.
- No business logic in repositories.

**AC covered**: AC-005 (tenant_id in every query — REQ-N-006 enforcement)

---

### TASK-005: Password hashing utility and AuthService · M/TDD · src/api/auth/auth_service.py,tests/unit/auth/test_auth_service.py

Implement `AuthService` as the business logic layer for authentication flows. It depends
on `UserRepository`, `RefreshTokenRepository`, and `TokenService` — all injected via
constructor.

**Tests to write first (TDD)**:
- `test_login_valid_credentials_returns_access_and_refresh_tokens` — mock user with known bcrypt hash; assert `TokenResponse` and that `RefreshTokenRepository.create` was called.
- `test_login_wrong_password_raises_unauthorized` — verify bcrypt verify returns False; service raises `AuthenticationError`; no token issued.
- `test_login_unknown_email_raises_unauthorized` — `UserRepository.get_by_email` returns None; raises same `AuthenticationError` with identical message (no email oracle).
- `test_login_uses_constant_time_comparison` — even on unknown email, a dummy bcrypt verify is performed to prevent timing oracle (see implementation note).
- `test_refresh_valid_token_returns_new_access_token` — active token in DB; raw token matches hash; issues new access token.
- `test_refresh_revoked_token_raises_unauthorized`
- `test_refresh_expired_token_raises_unauthorized`
- `test_logout_revokes_token`
- `test_password_hash_uses_bcrypt_rounds_gte_12` — call `hash_password`; decode the bcrypt string and inspect cost factor.

Implementation:
- `login(email, password, tenant_id) -> tuple[str, UUID, str]` — returns `(access_token, refresh_token_id, raw_refresh_token)`.
- Timing-safe: on unknown email, call `passlib.context.dummy_verify()` before raising to prevent timing-based user enumeration.
- `refresh(token_id, raw_token, tenant_id) -> str` — returns new access token; does NOT rotate refresh token (MVP simplicity; rotation is a future hardening task).
- `logout(token_id, tenant_id) -> None` — revokes the single refresh token.
- Never log email, password, tokens, or hashes.

**AC covered**: AC-001, AC-002, AC-006

---

### TASK-006: AuthRouter — login, refresh, logout endpoints · M/TDD · src/api/auth/router.py,src/api/auth/schemas.py,tests/integration/auth/test_auth_router.py

Implement the three auth HTTP endpoints as a FastAPI `APIRouter`. Schemas live in
`schemas.py`. Rate limiting is applied via SlowAPI decorators (built in TASK-007).

**Tests to write first (TDD)**:

All integration tests hit the FastAPI `TestClient` (or `httpx.AsyncClient`) with a real
in-memory SQLite or test-PostgreSQL DB.

- `test_login_valid_credentials_returns_200_with_access_token` — response body has `access_token`, `token_type="bearer"`, `expires_in`; Set-Cookie header has `refresh_token` with `HttpOnly; SameSite=Strict`.
- `test_login_invalid_password_returns_401_generic_message` — body must not say "wrong password" or "user not found"; message is a fixed string.
- `test_login_unknown_email_returns_401_same_message` — identical error body to wrong-password case (no oracle).
- `test_login_missing_fields_returns_422`
- `test_refresh_valid_cookie_returns_200_new_access_token`
- `test_refresh_missing_cookie_returns_401`
- `test_refresh_revoked_token_returns_401`
- `test_logout_returns_204_and_clears_cookie` — response has `Set-Cookie: refresh_token=; Max-Age=0`.

Endpoint specifications:
- `POST /api/v1/auth/login` — body: `LoginRequest`; success: 200 `TokenResponse` + Set-Cookie `refresh_token=<raw>; HttpOnly; SameSite=Strict; Path=/api/v1/auth/refresh`; failure: 401.
- `POST /api/v1/auth/refresh` — reads `refresh_token` from HttpOnly cookie; success: 200 `TokenResponse`; failure: 401.
- `POST /api/v1/auth/logout` — reads cookie; revokes token; 204 + clears cookie.
- Error responses use the standard envelope: `{"data": null, "error": {"code": "UNAUTHORIZED", "message": "..."}}`.
- Stack traces never returned to clients.

**AC covered**: AC-001, AC-002

---

### TASK-007: Rate limiting on auth endpoints · S/no-TDD · src/api/middleware/rate_limit.py,src/api/auth/router.py,src/api/main.py

Implement IP-based rate limiting using SlowAPI (a FastAPI-compatible wrapper around
`limits`).

- Instantiate a global `Limiter(key_func=get_remote_address)` in `src/api/middleware/rate_limit.py`.
- Register the limiter on the FastAPI `app` object and attach the `_rate_limit_exceeded_handler` (returns 429 JSON with the standard error envelope).
- Apply `@limiter.limit("10/minute")` to `POST /api/v1/auth/login`.
- Apply `@limiter.limit("30/minute")` to `POST /api/v1/auth/refresh`.
- Rate limit state stored in Redis (pass the Redis URL from settings to the `Limiter` storage URI).
- On limit exceeded, response is 429 with body `{"data": null, "error": {"code": "RATE_LIMITED", "message": "Too many requests"}}`.

No TDD flag: the behaviour of SlowAPI internals is not unit-testable; the integration
test in TASK-006's test suite adds one smoke test for the 429 path using a mock limiter
override.

**AC covered**: AC-003

---

### TASK-008: JWT authentication dependency and role guards · M/TDD · src/api/auth/dependencies.py,tests/unit/auth/test_dependencies.py

Implement three FastAPI dependencies:

1. `get_current_user(token, db) -> User` — extracts Bearer token from `Authorization` header, calls `TokenService.decode_access_token`, loads user from `UserRepository` using `user_id` and `tenant_id` from token claims (IDOR guard), raises `HTTP 401` if token invalid/expired or user not found.
2. `require_admin(current_user) -> User` — raises `HTTP 403` if `current_user.role != UserRole.admin`.
3. `require_operator_or_above(current_user) -> User` — raises `HTTP 403` if `current_user.role == UserRole.end_user`.

**Tests to write first (TDD)**:
- `test_get_current_user_valid_token_returns_user` — mock `TokenService.decode_access_token` and `UserRepository.get_by_id`; asserts correct user returned.
- `test_get_current_user_expired_token_raises_401`
- `test_get_current_user_tampered_token_raises_401`
- `test_get_current_user_user_not_found_in_db_raises_401` — token valid but `get_by_id` returns None; HTTP 401 (avoids user enumeration).
- `test_get_current_user_tenant_mismatch_raises_401` — `token.tenant_id != user.tenant_id`; HTTP 401 (IDOR guard).
- `test_require_admin_passes_for_admin_role`
- `test_require_admin_raises_403_for_operator`
- `test_require_admin_raises_403_for_end_user`
- `test_require_operator_or_above_passes_for_admin`
- `test_require_operator_or_above_passes_for_operator`
- `test_require_operator_or_above_raises_403_for_end_user`

**AC covered**: AC-004

---

### TASK-009: Wire auth module into FastAPI application · XS/no-TDD · src/api/main.py,src/api/auth/__init__.py

Register the `auth_router` on the FastAPI application under `/api/v1`. Register the
SlowAPI `Limiter` middleware and the 429 exception handler. Ensure `get_db` async session
dependency is available (create `src/api/dependencies.py` with the `AsyncSession` factory
if it does not exist). Export `get_current_user`, `require_admin`, and
`require_operator_or_above` from `src/api/auth/__init__.py` so other modules can import
the guards from a single, stable location.

**AC covered**: AC-001 (endpoints reachable), AC-003 (limiter wired), AC-004 (guards exported)

---

### TASK-010: Seed script for initial admin user · XS/no-TDD · src/db/seeds/seed_admin.py

Write a one-off CLI script (`python -m src.db.seeds.seed_admin`) that creates the first
admin user from environment variables `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, and
`SEED_TENANT_ID`. The script: validates env vars are present, hashes the password with
`CryptContext` at `BCRYPT_ROUNDS`, inserts one `user` row with `role=admin`, and prints
confirmation without echoing the password. Idempotent: if the email already exists for
the tenant, skip silently. Fails fast if `SEED_ADMIN_PASSWORD` is shorter than 12
characters.

**AC covered**: AC-006 (bcrypt storage verified in practice via seed path)

## Acceptance Criteria Coverage

- AC-001: Valid credentials return a JWT access token (expires_in ≤ 900 seconds) and a
  refresh token → TASK-003, TASK-005, TASK-006
- AC-002: Invalid credentials return HTTP 401 with a generic message (no email/password
  oracle) → TASK-005, TASK-006
- AC-003: More than 10 login requests from the same IP within 60 seconds → HTTP 429 →
  TASK-007
- AC-004: Request to admin panel endpoint with role=end_user → HTTP 403 → TASK-008
- AC-005: user table includes non-nullable role enum column and non-nullable tenant_id
  column → TASK-001
- AC-006: Stored password is bcrypt-hashed at ≥ 12 rounds; no plaintext in DB →
  TASK-003, TASK-005, TASK-010

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | What is the precise boundary between MVP username/password auth and "OAuth2 production" auth? When does the OAuth2 migration trigger? | Resolved by D2: OAuth2 is post-MVP only. The user table schema is OAuth2-compatible by design (no columns need adding). The migration trigger is a business decision outside this plan's scope. This plan implements username/password + JWT exclusively. |

## Risks and Notes

- **Refresh token rotation not implemented in MVP.** The refresh endpoint issues a new
  access token but keeps the same refresh token active. Token rotation (issuing a new
  refresh token and revoking the old one on every use) is a hardening measure to add
  post-MVP. The current approach is documented to avoid developer surprise.
- **Single tenant in MVP.** `tenant_id` must still be threaded through every query.
  The seed script and test fixtures must provide a real UUID — do not use a null or
  placeholder. Multi-tenant activation requires no schema migration (Principle 3).
- **SlowAPI in-process limiter vs. distributed Redis limiter.** If the API scales to
  multiple instances, in-process rate limiting (the default SlowAPI backend) will allow
  N × 10 attempts per window. TASK-007 wires the Redis storage URI to prevent this.
  Confirm `REDIS_URL` is set in all environments.
- **bcrypt and async.** `passlib` bcrypt is synchronous and CPU-bound. At cost factor 12,
  one `verify` call takes ~200–300 ms. Run `verify` and `hash` in `asyncio.get_event_loop().run_in_executor(None, ...)` or use
  `anyio.to_thread.run_sync` to avoid blocking the event loop in production.
- **`python-jose` vs `PyJWT`.** Either library is acceptable; `python-jose` is preferred
  because it is already a common FastAPI ecosystem dependency. Do not mix both.
- **No HTTPS enforcement in this plan.** HttpOnly cookies require HTTPS in production to
  prevent cookie theft. HTTPS termination is handled at the reverse proxy / container
  layer (outside this plan's scope) but must be verified before deployment.
- **Password field length.** bcrypt output is always 60 characters. `VARCHAR(72)` gives
  headroom for any future prefix. Never store raw passwords under any column name.
