---
plan_id: PLAN-N-006
slug: multitenancy-security
title: Multi-Tenancy and Security Isolation
linked_requirement: REQ-N-006
type: non-functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-033, reason: "JWT and role field foundation — user table, TokenService, RefreshTokenRepository, rate-limit middleware, and get_current_user dependency all provided by PLAN-F-033" }
brainstorm_decisions:
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-006 — Multi-Tenancy and Security Isolation

## Linked Requirement
**REQ-N-006** — Multi-Tenancy and Security Isolation
Status: approved | Jira: (blank)

## Objective

Harden the system against cross-tenant data access and IDOR vulnerabilities by introducing
a typed repository base class that structurally enforces `tenant_id` on every query, a
reusable ownership-check utility for resource endpoints, extended rate-limit coverage for
portfolio mutation and admin endpoints, a DB-level `CHECK` constraint that prevents raw
credentials from ever entering `source_config.credentials_ref`, and a dedicated security
test module that exercises all five acceptance criteria. PLAN-F-033 already delivers the
`user` table, JWT issuance/validation, `get_current_user` dependency, bcrypt hashing, and
rate limiting on the two auth endpoints; this plan builds the cross-cutting enforcement
layer on top of those foundations.

## Architecture Context

This plan touches four modules (Architecture §5):

- **`storage`** — new `TenantScopedRepository` abstract base class that every concrete
  repository subclasses; it wraps SQLAlchemy `select`/`update`/`delete` builders to
  always inject `WHERE tenant_id = :tenant_id`. This is the primary enforcement point for
  AC-001.
- **`api`** — new `ownership.py` module providing the `verify_resource_ownership` utility
  and a `ResourceOwnerDepends` FastAPI dependency factory used on every URL-parameterised
  endpoint (e.g., `/portfolio/{id}`, `/company/{id}`). Extended rate-limit registrations
  for `POST /portfolio/positions` and admin mutation endpoints.
- **`db/migrations`** — one new Alembic migration that adds a PostgreSQL `CHECK` constraint
  to `source_config.credentials_ref`, enforcing the `env:` or `vault:` prefix pattern so
  raw API key strings are rejected at the DB level.
- **`tests/security`** — a dedicated security test package with targeted tests for IDOR,
  tenant isolation, credential constraint, rate limiting, and JWT TTL.

Architecture §12.3 (Multi-Tenancy) mandates: all repository queries include `tenant_id`
in the WHERE clause. Architecture §12.1 (Authentication) mandates: resource ownership
verified on every lookup. Architecture §12.2 (Secrets Management, D3) mandates:
`credentials_ref` stores only a vault-reference string. Architecture §13 mandates
SQLAlchemy 2.0 async ORM for all DB access.

Layering rule (Architecture §5): this plan sits at the `storage` and `api` cross-cutting
layers; it does not introduce new business logic. The `TenantScopedRepository` is a pure
infrastructure concern, not a service.

## Component Design

### New Components

```
src/
  storage/
    repositories/
      base.py                   — TenantScopedRepository: abstract base class with
                                  _select(), _update_where(), _delete_where() helpers that
                                  always inject tenant_id; raises TenantIdMissingError when
                                  called without tenant_id argument
  api/
    security/
      __init__.py
      ownership.py              — verify_resource_ownership(resource, tenant_id, user_id)
                                  + ResourceOwnerDepends factory for FastAPI Depends
  db/
    migrations/
      versions/
        0003_credentials_ref_check_constraint.py
                                — Alembic migration adding CHECK on
                                  source_config.credentials_ref

tests/
  security/
    __init__.py
    test_tenant_isolation.py    — tenant_id filter enforcement tests (unit + integration)
    test_idor_prevention.py     — cross-tenant URL access tests
    test_credentials_constraint.py  — vault-ref-only enforcement test
    test_rate_limiting.py       — rate limit 429 tests for all covered endpoints
    test_jwt_ttl.py             — JWT TTL ≤15 min test + expired token 401 test
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/storage/repositories/user_repository.py` | Inherit from `TenantScopedRepository` instead of plain `object` | Enforce base class contract on existing repository |
| `src/storage/repositories/refresh_token_repository.py` | Inherit from `TenantScopedRepository` | Enforce base class contract on existing repository |
| `src/api/middleware/rate_limit.py` | Add `@limiter.limit("100/minute")` helper for portfolio write endpoints; add `@limiter.limit("60/minute")` helper for admin mutation endpoints | Extend rate-limit coverage per REQ-N-006 spec |
| `src/api/auth/router.py` | Import and apply `ResourceOwnerDepends` pattern documentation; no functional change needed (auth routes have no resource IDs) | Documentation alignment only |

### Interfaces and Contracts

```python
# src/storage/repositories/base.py

class TenantIdMissingError(Exception):
    """Raised when a repository method is invoked without tenant_id."""

class TenantScopedRepository:
    """Abstract base for all repositories that touch user-owned tables.

    Concrete subclasses call self._scoped_select(Model) and
    self._scoped_delete(Model) to get pre-filtered query builders.
    Calling these methods without a valid tenant_id UUID raises
    TenantIdMissingError immediately — before any DB round-trip.
    """

    def _scoped_select(self, model: type, tenant_id: UUID) -> Select:
        """Return select(model).where(model.tenant_id == tenant_id).
        Raises TenantIdMissingError if tenant_id is None."""

    def _scoped_update(self, model: type, tenant_id: UUID) -> Update:
        """Return update(model).where(model.tenant_id == tenant_id).
        Raises TenantIdMissingError if tenant_id is None."""

    def _scoped_delete(self, model: type, tenant_id: UUID) -> Delete:
        """Return delete(model).where(model.tenant_id == tenant_id).
        Raises TenantIdMissingError if tenant_id is None."""


# src/api/security/ownership.py

class ResourceNotOwnedError(Exception):
    """Raised when tenant_id on a resource does not match the requesting tenant."""

def verify_resource_ownership(
    resource: Any,                # any ORM object with a .tenant_id attribute
    requesting_tenant_id: UUID,
    resource_id: UUID | str,      # for error messages only
) -> None:
    """Raise ResourceNotOwnedError if resource.tenant_id != requesting_tenant_id.

    Callers convert ResourceNotOwnedError to HTTP 404 (preferred — avoids
    disclosing that the resource exists) or HTTP 403. Never HTTP 200 with
    empty body.
    """

def resource_owner_dependency(
    get_resource_fn: Callable[[UUID, UUID], Awaitable[Any]],
) -> Callable:
    """Factory returning a FastAPI Depends that: (1) fetches the resource
    using the tenant_id from get_current_user, (2) calls
    verify_resource_ownership, (3) returns the resource or raises HTTP 404.

    Usage:
        get_portfolio = resource_owner_dependency(portfolio_repo.get_by_id)

        @router.get("/portfolio/{portfolio_id}")
        async def get_portfolio_endpoint(
            portfolio_id: UUID,
            portfolio: Portfolio = Depends(get_portfolio),
        ): ...
    """
```

## Implementation Tasks

### TASK-001: TenantScopedRepository base class · M/TDD · src/storage/repositories/base.py,tests/security/test_tenant_isolation.py

Implement `TenantScopedRepository` as an abstract base class for SQLAlchemy 2.0 async
repositories. The class provides three protected helpers (`_scoped_select`,
`_scoped_update`, `_scoped_delete`) that each accept a SQLAlchemy model class and a
`tenant_id: UUID` argument. If `tenant_id` is `None` or missing, the helper raises
`TenantIdMissingError` immediately — before building the query. This makes it structurally
impossible for a subclass to accidentally omit the tenant filter: the query object cannot
be constructed without providing the tenant.

The helpers return SQLAlchemy `Select`, `Update`, and `Delete` objects (respectively) with
the `WHERE tenant_id = :tenant_id` clause already attached. Subclasses chain additional
conditions on top: `self._scoped_select(User, tenant_id).where(User.email == email)`.

`TenantIdMissingError` is a domain error defined in `base.py` and re-exported from
`src/storage/repositories/__init__.py`.

**Tests to write first (TDD)**:
- `test_scoped_select_raises_when_tenant_id_is_none` — call `_scoped_select(User, None)`; expect `TenantIdMissingError`.
- `test_scoped_update_raises_when_tenant_id_is_none` — same pattern for update.
- `test_scoped_delete_raises_when_tenant_id_is_none` — same pattern for delete.
- `test_scoped_select_includes_tenant_id_in_where_clause` — inspect the compiled SQL string for `tenant_id`; verify the clause is present and the value matches the supplied UUID.
- `test_scoped_update_includes_tenant_id_in_where_clause`
- `test_scoped_delete_includes_tenant_id_in_where_clause`
- `test_concrete_repository_subclass_cannot_omit_tenant_filter` — implement a minimal concrete subclass that calls `_scoped_select` without tenant_id; assert `TenantIdMissingError` before the session is ever opened (no DB required).

**AC covered**: AC-001

---

### TASK-002: Migrate existing repositories to TenantScopedRepository · M/TDD · src/storage/repositories/user_repository.py,src/storage/repositories/refresh_token_repository.py,tests/security/test_tenant_isolation.py

Refactor `UserRepository` and `RefreshTokenRepository` (produced by PLAN-F-033) to
inherit from `TenantScopedRepository` and replace any raw `select(Model).where(...)` calls
with the corresponding `_scoped_select`, `_scoped_update`, `_scoped_delete` helpers. All
`tenant_id` filtering that was done manually is now delegated to the base class.

The public interface of both repositories remains identical — no callers need to change.

**Tests to write first (TDD)**:
- `test_user_repository_inherits_tenant_scoped_repository` — `issubclass(UserRepository, TenantScopedRepository)` is `True`.
- `test_user_repository_get_by_email_uses_scoped_select` — mock `_scoped_select`; verify it is called with `tenant_id`; assert `TenantIdMissingError` propagates correctly when `tenant_id=None` is passed.
- `test_user_repository_get_by_id_uses_scoped_select`
- `test_refresh_token_repository_inherits_tenant_scoped_repository`
- `test_refresh_token_repository_get_active_uses_scoped_select`
- `test_refresh_token_repository_revoke_uses_scoped_update`
- `test_refresh_token_repository_revoke_all_uses_scoped_update`

Integration (real test DB — re-uses existing fixtures from PLAN-F-033):
- `test_user_get_by_email_cross_tenant_returns_none` — re-run the PLAN-F-033 cross-tenant integration test to confirm behaviour is preserved post-refactor.
- `test_refresh_token_cross_tenant_returns_none` — insert token under tenant_A; query under tenant_B; expect `None`.

**AC covered**: AC-001

---

### TASK-003: IDOR prevention — ownership check utility · M/TDD · src/api/security/ownership.py,src/api/security/__init__.py,tests/security/test_idor_prevention.py

Implement `verify_resource_ownership` and `resource_owner_dependency` as specified in the
Component Design section. The utility checks that `resource.tenant_id` equals
`requesting_tenant_id`; if not, it raises `ResourceNotOwnedError`. Callers (routers) catch
`ResourceNotOwnedError` and return HTTP 404 (preferred) rather than HTTP 403 to avoid
disclosing resource existence to cross-tenant callers.

`resource_owner_dependency` is a factory that returns a FastAPI `Depends`-compatible async
function. It accepts `get_resource_fn: Callable[[UUID, UUID], Awaitable[T]]` (signature:
`async def fn(resource_id, tenant_id) -> T | None`) and returns a dependency that:
1. Resolves `current_user` via `get_current_user`.
2. Calls `get_resource_fn(resource_id, current_user.tenant_id)`.
3. Returns `None`-as-404 if the resource is not found (repository already scoped by tenant).
4. Calls `verify_resource_ownership` as a second-line defence (catches any repository
   implementation that returns a cross-tenant object despite the tenant filter).
5. Returns the resource object on success.

**Tests to write first (TDD)**:
- `test_verify_resource_ownership_passes_for_matching_tenant` — resource with `tenant_id=A`, requesting `tenant_id=A`; no exception raised.
- `test_verify_resource_ownership_raises_for_mismatched_tenant` — resource with `tenant_id=A`, requesting `tenant_id=B`; `ResourceNotOwnedError` raised.
- `test_verify_resource_ownership_raises_for_none_resource_tenant` — resource with `tenant_id=None`; raises `ResourceNotOwnedError`.
- `test_resource_owner_dependency_returns_resource_when_owned` — mock `get_resource_fn` returning a resource with matching tenant; dependency returns the resource.
- `test_resource_owner_dependency_raises_404_when_resource_not_found` — `get_resource_fn` returns `None`; HTTP 404.
- `test_resource_owner_dependency_raises_404_when_tenant_mismatch` — `get_resource_fn` returns resource with wrong `tenant_id` (simulating a buggy repo); HTTP 404.
- Integration test (`test_cross_tenant_url_access_returns_404`): create portfolio under `tenant_A`; authenticate as `tenant_B` user; `GET /api/v1/portfolio/{id}`; assert 404. (Uses FastAPI `TestClient` with two distinct test users and a minimal portfolio router stub that applies the dependency.)

**AC covered**: AC-002

---

### TASK-004: source_config credentials_ref constraint · M/TDD · src/db/migrations/versions/0003_credentials_ref_check_constraint.py,src/storage/models/source_config.py,tests/security/test_credentials_constraint.py

Add a PostgreSQL `CHECK` constraint to `source_config.credentials_ref` that rejects any
value not matching the pattern `^(env|vault):[A-Z0-9_]+$`. This is a DB-level enforcement
of Architecture decision D3: vault-reference stubs only, never raw API keys.

The Alembic migration (script `0003`) uses `op.create_check_constraint`:

```python
op.create_check_constraint(
    "ck_source_config_credentials_ref_prefix",
    "source_config",
    "credentials_ref ~ '^(env|vault):[A-Z0-9_]+$'",
)
```

If `source_config` does not yet exist (pre-PLAN-F-028), the migration must be conditional:
check `op.get_bind().dialect.has_table(...)` and skip gracefully. Add a note in the
migration docstring that `source_config` is created by PLAN-F-028.

The SQLAlchemy ORM model `SourceConfig` (create it if not present from a prior plan, or
extend if it exists) adds a Python-level `@validates("credentials_ref")` event that checks
the same regex and raises `ValueError` before the DB roundtrip, giving callers a
programmatic error rather than a DB constraint error.

**Tests to write first (TDD)**:
- `test_credentials_ref_orm_validator_accepts_env_prefix` — `SourceConfig(credentials_ref="env:FINNHUB_API_KEY")`; no error.
- `test_credentials_ref_orm_validator_accepts_vault_prefix` — `SourceConfig(credentials_ref="vault:MY_SECRET")`; no error.
- `test_credentials_ref_orm_validator_rejects_raw_key` — `SourceConfig(credentials_ref="sk-abc123")`; raises `ValueError`.
- `test_credentials_ref_orm_validator_rejects_empty_string` — raises `ValueError`.
- `test_credentials_ref_orm_validator_rejects_env_lowercase` — `SourceConfig(credentials_ref="env:finnhub_api_key")`; raises `ValueError` (pattern requires upper-case key).
- Integration test (`test_credentials_ref_db_constraint_rejects_raw_key`): attempt to insert a `source_config` row with `credentials_ref="ABCDEF123"` directly via `session.execute(insert(...))`; catch `sqlalchemy.exc.IntegrityError` and assert it contains the constraint name.

**AC covered**: AC-003

---

### TASK-005: Extended rate limiting for portfolio and admin mutation endpoints · S/no-TDD · src/api/middleware/rate_limit.py,src/api/security/__init__.py

Extend `src/api/middleware/rate_limit.py` with two pre-configured limit decorators:

```python
# 100 per minute per user (keyed by user_id extracted from JWT, not by IP)
portfolio_write_limit = limiter.limit("100/minute", key_func=get_user_id_from_request)

# 60 per minute per admin user
admin_mutation_limit = limiter.limit("60/minute", key_func=get_user_id_from_request)
```

`get_user_id_from_request` is a helper that reads the Bearer token from the
`Authorization` header, decodes it (no DB call — pure JWT decode), and returns the
`sub` claim string. If decoding fails, falls back to `get_remote_address` so unauthenticated
requests are still IP-rate-limited.

Export `portfolio_write_limit` and `admin_mutation_limit` from
`src/api/security/__init__.py` alongside `verify_resource_ownership` and
`resource_owner_dependency` so that all security decorators share one import path.

These decorators are applied at the router level in later feature plans (PLAN-F-024,
PLAN-F-028, PLAN-F-030) when those routers are implemented. This task delivers only the
reusable decorator infrastructure.

Note: No TDD flag because the SlowAPI decorator mechanism is an external framework concern
not amenable to unit testing; instead, TASK-006 includes integration smoke tests for each
rate limit tier via a test router stub.

**AC covered**: AC-004 (partial — decorator infrastructure; rate limit smoke tests in TASK-006)

---

### TASK-006: Security test suite — rate limiting and JWT TTL · L/TDD · tests/security/test_rate_limiting.py,tests/security/test_jwt_ttl.py

Implement the remaining security tests that span multiple enforcement points.

**`tests/security/test_rate_limiting.py`**

Tests to write first (TDD):
- `test_login_rate_limit_11th_request_returns_429` — fire 11 `POST /api/v1/auth/login` requests from the same IP within a single rate-limit window; assert the 11th returns HTTP 429.
- `test_login_rate_limit_window_resets` — after the 10 requests that would trigger the limit, fast-forward the Redis TTL (or use `fakeredis` time control) by 61 seconds; assert the next request succeeds with 200 or 401 (not 429).
- `test_refresh_rate_limit_31st_request_returns_429` — same pattern for `POST /api/v1/auth/refresh` at 30/minute.
- `test_portfolio_write_rate_limit_101st_request_returns_429` — uses a minimal test router stub registered under `/test-portfolio/positions` with `portfolio_write_limit` applied; fire 101 authenticated requests; assert 101st is 429.
- `test_admin_mutation_rate_limit_61st_request_returns_429` — same with `admin_mutation_limit` on a test stub admin route.

Use `fakeredis` for the rate-limit storage backend in tests to avoid real Redis dependency
and enable time travel.

**`tests/security/test_jwt_ttl.py`**

Tests to write first (TDD):
- `test_access_token_expires_within_15_minutes` — call `TokenService.create_access_token`; decode the JWT; assert `exp - iat <= 900` seconds.
- `test_expired_access_token_returns_401` — create a token with `exp = now - 1 second`; pass it as Bearer to any protected endpoint; assert HTTP 401.
- `test_access_token_with_no_tenant_id_claim_returns_401` — craft a JWT without `tenant_id` claim; assert HTTP 401.
- `test_access_token_with_no_role_claim_returns_401` — craft a JWT without `role` claim; assert HTTP 401.

**AC covered**: AC-004 (full coverage for all four rate-limit tiers), AC-005

---

## Acceptance Criteria Coverage

- AC-001: Repository methods always include tenant_id in WHERE clause; omitting tenant_id raises TenantIdMissingError → TASK-001, TASK-002
- AC-002: Cross-tenant URL access returns HTTP 403 or 404 → TASK-003
- AC-003: source_config.credentials_ref accepts only vault-reference strings; raw API keys rejected → TASK-004
- AC-004: Login endpoint rate-limited at 10/minute; 11th request returns HTTP 429; all four rate-limit tiers tested → TASK-005, TASK-006
- AC-005: JWT access token expires within 15 minutes; expired token returns HTTP 401 → TASK-006

## Risks and Notes

- **Migration 0003 ordering.** The `CHECK` constraint migration depends on the `source_config` table created by PLAN-F-028. If PLAN-N-006 is executed before PLAN-F-028, the migration must skip gracefully. The migration script includes an existence check. Execution order in the plans-index places PLAN-N-006 in Wave 1 alongside PLAN-F-028 — coordinate execution sequence.
- **TenantScopedRepository and geo_event.** `geo_event` uses `tenant_id = NULL` for global events (Architecture §12.3). The `_scoped_select` helper must not be used on `geo_event` queries that are meant to be global; those queries bypass `TenantScopedRepository` and apply their own `WHERE (tenant_id = :tid OR tenant_id IS NULL)` logic. Document this exception clearly in `base.py`.
- **`get_user_id_from_request` fallback.** When the JWT is absent or malformed, falling back to IP-based rate limiting is intentional (unauthenticated callers must still be rate-limited). The fallback must not log the raw token string.
- **Test isolation for rate-limit tests.** `fakeredis` must be injected as the SlowAPI storage backend in the test configuration. The `conftest.py` fixture must patch the `Limiter` storage before any route is imported so the `@limiter.limit(...)` decorator picks up the fake backend.
- **No database-level row security policies.** Application-level tenant filter is the enforcement mechanism for MVP per the requirement's out-of-scope declaration. `TenantScopedRepository` is the chosen implementation vehicle.
- **Refresh token rotation deferred.** As noted in PLAN-F-033, refresh token rotation (one-time use) is post-MVP hardening. REQ-N-006 requires the tokens to be stored hashed (delivered by PLAN-F-033) and one-time-use rotation to be applied. This plan does not implement rotation but documents it as a known gap. A follow-up task should be created for post-MVP token rotation.
