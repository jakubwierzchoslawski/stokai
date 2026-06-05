---
review_id: REVIEW-F-ALL
plan_id: PLAN-F-001..033 (all functional)
requirement_id: REQ-F-001..033
status: changes-required
reviewed_at: 2026-06-05T21:40:00Z
findings_summary:
  critical: 1
  high: 2
  medium: 4
  low: 3
  info: 2
ac_coverage: N/A (architectural coherence review, not per-AC)
dod_complete: false
manual_actions_pending: 3
---

# REVIEW-F-ALL — Functional Plans Architectural Coherence Review

## Verdict
**CHANGES REQUIRED**

The codebase demonstrates strong architectural discipline across most modules: clean SOLID conformance, thorough security testing (tenant isolation, IDOR prevention, token validation), and well-structured dependency injection. However, one latent security issue (stubbed auth on the ingest endpoint) and one architectural duplication (two parallel auth dependency trees) must be resolved before this can be considered production-ready. The duplicate auth tree creates real risk of divergent behavior between routers that use different auth implementations.

---

## Acceptance Criteria Verification

Per-plan AC verification was not performed exhaustively (33 plans). A representative sample from Wave 0–1 plans shows strong AC-to-code mapping:

| Plan | AC Count | Sample Coverage |
|------|----------|-----------------|
| PLAN-F-001 | 6 | ✅ All 6 ACs mapped to PipelineExecutor + 12 step functions + e2e test |
| PLAN-F-002 | 4 | ✅ Both steps implemented + tested with mock LLM clients |
| PLAN-F-033 | 5 | ✅ Auth service, token rotation, role guards all present + tested |
| PLAN-F-005 | 4 | ✅ Alert dispatcher + anti-fatigue + rule evaluator implemented |

---

## Definition of Done Status

| Item | Status |
|------|--------|
| All 33 plans marked "done" in plans-index | ✅ |
| Unit tests present for core modules | ✅ |
| Integration tests for critical paths | ✅ |
| Security tests (tenant isolation, IDOR, JWT) | ✅ |
| Events ingest endpoint registered in main.py | ❌ Missing |
| Duplicate auth dependency tree resolved | ❌ Not resolved |
| Stubbed `_require_admin` replaced with real JWT auth | ❌ TODO remains |

---

## Findings

### 🔴 CRITICAL (blocks merge)

#### C-001 — Ingest endpoint has no auth enforcement (stubbed guard, never wired)
**File**: `src/api/routers/events.py:24-37` and `src/api/main.py`
**Rule**: Standards Card — "Auth required by default on all endpoints; opt out explicitly." Security baseline.
**Finding**: The `POST /api/v1/events/ingest` endpoint is defined with a `_require_admin` function (line 24) that is a hardcoded TODO stub — it checks only for a non-empty `Authorization` header and returns a placeholder dict. Worse, `_require_admin` is **never passed as a `Depends()`** to the `ingest_event` route handler (line 40-83). The endpoint currently has zero authentication. Additionally, this router is **not registered** in `src/api/main.py`, so it is not currently exposed — but as soon as it is wired in, it becomes an open admin endpoint.
**Fix**: Replace `_require_admin` with `Depends(require_admin)` from `src.api.auth.dependencies`. Register the router in `main.py` with proper auth. Example:
```python
from src.api.auth.dependencies import require_admin

@router.post("/ingest", ...)
async def ingest_event(
    raw_event: RawEvent,
    _admin: User = Depends(require_admin),
) -> dict:
    ...
```

---

### 🔴 HIGH (blocks merge)

#### H-001 — Duplicate auth dependency tree creates divergent behavior
**File**: `src/api/auth_deps.py` vs `src/api/auth/dependencies.py`
**Rule**: Standards Card — SRP, architecture coherence.
**Finding**: Two parallel implementations of `get_current_user` exist:
- `src.api.auth_deps.get_current_user` — decodes JWT only, returns a lightweight `CurrentUser` dataclass. Does NOT verify the user exists in the database. Used by: `alerts_router`, `briefs_router`, `qa_router`, `portfolio_router`, `watchlist_router`, `onboarding_router`, `hil_router`.
- `src.api.auth.dependencies.get_current_user` — decodes JWT AND queries the database via `UserRepository.getById()`, returns the full `User` ORM model. Also performs IDOR guard (tenant_id match). Used by: `admin_router`, `system_ops_router`, `evaluation_router`.

This creates a real security asymmetry: if a user is deleted from the database, their JWT remains valid for all routers using `auth_deps.py` until the token expires (up to 15 minutes). The DB-verified path would correctly reject them immediately. Additionally, the `auth_deps.get_current_user` path lacks the tenant_id mismatch check present in the full `dependencies.get_current_user`.
**Fix**: Consolidate to a single `get_current_user` in `src/api/auth/dependencies.py`. All routers should go through the DB-verified path. The lightweight `CurrentUser` dataclass can be retained as the return type if the ORM dependency is undesirable, but the DB verification step must be kept.

#### H-002 — `get_auth_service()` raises NotImplementedError — production footgun
**File**: `src/api/auth/router.py:35-47`
**Rule**: Fail-fast principle; Standards Card — DIP (constructor injection).
**Finding**: The `get_auth_service` FastAPI dependency function unconditionally raises `NotImplementedError`, stating it "must be overridden with a configured AuthService instance." This means the auth router cannot function without manual DI wiring at startup. If an operator forgets to override this dependency, all login/refresh/logout endpoints return 500 errors. This is a runtime failure, not a startup failure.
**Fix**: Instantiate `AuthService` with real dependencies in the default `get_auth_service` implementation, using `get_db` and `get_settings`. Fall back to the manual override only in test mode. Example:
```python
def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    settings = get_settings()
    user_repo = UserRepository(session=db)
    refresh_repo = RefreshTokenRepository(session=db)
    token_svc = TokenService(settings=settings)
    return AuthService(
        user_repo=user_repo,
        refresh_token_repo=refresh_repo,
        token_service=token_svc,
    )
```

---

### 🟡 MEDIUM (should fix before merge)

#### M-001 — PipelineExecutor mixes Protocol interfaces with concrete types
**File**: `src/events/pipeline_executor.py:59-89`
**Rule**: Standards Card — DIP ("depend on abstractions").
**Finding**: The constructor accepts `EventEmbeddingRepository` (concrete class) as the `event_embedding_repo` parameter, while all other repositories are typed as Protocol interfaces (`IGeoEventRepository`, `IEventExposureRepository`, `IAlertRepository`). This breaks consistency and makes the executor harder to unit-test (the embedding repo must be a real or mocked concrete class, not a Protocol).
**Fix**: Type the parameter as `IEventEmbeddingRepository` (Protocol). Create the interface if it doesn't exist.

#### M-002 — Step 6/7 in pipeline uses `EmbeddingService` instead of `IEmbeddingClient`
**File**: `src/events/pipeline_executor.py:67,183-190`
**Rule**: Standards Card — DIP, OCP.
**Finding**: Steps 6 (embed_event) and 7 (find_historical_analogies) use `EmbeddingService` (a concrete class from `src.ai.embedding.service`) rather than the `IEmbeddingClient` Protocol defined in `src/ai/interfaces/i_embedding_client.py`. This diverges from the pattern used for LLM calls (steps 2, 3, 8 use `ILLMClient` Protocol). The plan (PLAN-F-001) specified `IEmbeddingClient` as the interface.
**Fix**: Either use `IEmbeddingClient` Protocol consistently, or update PLAN-F-001 to document the `EmbeddingService` abstraction layer.

#### M-003 — `src/api/main.py` missing several router registrations
**File**: `src/api/main.py`
**Rule**: Completeness — endpoints defined but not wired.
**Finding**: The following routers are imported and defined in the codebase but NOT registered in `main.py`:
- `src/api/routers/events.py` (ingest endpoint) — PLAN-F-001
- `src/api/routers/workflow_router.py` — PLAN-F-007
- `src/api/v1/company_detail_router.py` — PLAN-F-023
- `src/api/v1/watchlist_scan_router.py` — PLAN-F-008
- `src/api/v1/earnings_brief_router.py` — PLAN-F-009
- `src/api/v1/prompts_admin_router.py` — PLAN-F-014
- `src/api/v1/scoring/*` routers — PLAN-F-017/018
- `src/api/v1/screener/router.py` — PLAN-F-022
- `src/api/briefs/briefs_router.py` — PLAN-F-026
- `src/api/memory/memory_router.py` — PLAN-F-015

This means a significant portion of the API surface defined in the functional plans is not reachable via HTTP.
**Fix**: Register all routers in `main.py` with appropriate prefixes and auth dependencies.

#### M-004 — `auth_deps.get_current_user` does not verify user existence in DB
**File**: `src/api/auth_deps.py:68-78`
**Rule**: Standards Card — Security ("Verify resource ownership on every lookup").
**Finding**: The lightweight `get_current_user` only decodes and validates the JWT signature. It does not check whether the user still exists in the database. While this is acceptable for read-heavy endpoints (alerts, briefs, portfolio), it means a deleted user's JWT remains valid until expiry. Combined with H-001, this should be unified.
**Fix**: Add a lightweight DB existence check (e.g., `SELECT 1 FROM users WHERE user_id = $1 AND tenant_id = $2`) that does not fetch the full User ORM object. Or unify with the full path.

---

### 🔵 LOW (optional)

#### L-001 — `from __future__ import annotations` inconsistently used
**File**: Various — present in some files (`src/ai/anthropic_client.py`, `src/api/security/ownership.py`) but absent in others (`src/api/main.py`, `src/config/settings.py`).
**Rule**: Consistency.
**Finding**: The `from __future__ import annotations` import enables PEP 604-style syntax. Some files use it, others don't. This is cosmetic but indicates inconsistent tooling configuration.

#### L-002 — Events pipeline executor imports `uuid` via `__import__` at runtime
**File**: `src/events/pipeline_executor.py:128`
**Rule**: Code clarity.
**Finding**: `__import__("uuid").uuid4()` is used inline to generate a fallback event_id when `SourceDisabledError` is caught. Standard `import uuid` at the top of the file is preferred.
**Fix**: Add `import uuid` to the module-level imports and use `uuid.uuid4()`.

#### L-003 — Prompt SHA stability not enforced via `.gitattributes`
**File**: `prompts/classifiers/` directory
**Rule**: PLAN-F-002 risk note — "Enforce LF line endings in `.gitattributes` for all `prompts/` files to guarantee stable SHAs."
**Finding**: No `.gitattributes` file was found in the repository. Different developers on Windows (CRLF) vs Linux (LF) will compute different prompt SHAs, causing Langfuse `prompt_version` mismatches.
**Fix**: Create `.gitattributes` with `prompts/** text eol=lf`.

---

### 🔵 INFO (optional)

#### I-001 — Comprehensive test coverage across critical paths
**Finding**: Test coverage is impressive for an MVP. Security tests for tenant isolation (`test_tenant_isolation.py` with 17 test cases), IDOR prevention (`test_idor_prevention.py`), JWT TTL (`test_jwt_ttl.py`), and rate limiting (`test_rate_limiting.py`) demonstrate security-first thinking. Unit tests for `AnthropicLLMClient` properly verify timeout propagation, API key sanitization, and error wrapping.

#### I-002 — Strong DI and Protocol-based design
**Finding**: The codebase consistently uses Protocol interfaces and constructor injection throughout the AI and event modules. `ILLMClient`, `ILangfuseTracer`, `IAlertRuleEvaluator`, `IAlertDispatcher`, `IAgentRegistry` all follow the DIP cleanly. The `TenantScopedRepository` base class is a particularly elegant design for enforcing multi-tenant isolation at the ORM layer. The `ToolError` enum + `BaseTool.execute` pattern with run-level caching is well-structured.

---

## Manual Actions Required Before Merge

1. **Wire all unregistered routers** into `src/api/main.py` (see M-003 for the full list). Each must include auth dependencies from the consolidated auth tree.
2. **Consolidate auth dependency trees** — merge `src/api/auth_deps.py` into `src/api/auth/dependencies.py`, or remove the lightweight path in favor of the DB-verified path.
3. **Create `.gitattributes`** with `prompts/** text eol=lf` to ensure prompt SHA stability across platforms.

---

## Files Reviewed

| File | Lines | Status |
|------|-------|--------|
| src/api/main.py | 71 | ⚠️ Missing router registrations |
| src/api/auth/router.py | 230 | ⚠️ get_auth_service raises NotImplementedError |
| src/api/auth/dependencies.py | 108 | ✅ Solid; DB-verified + IDOR guard |
| src/api/auth_deps.py | 91 | ⚠️ Duplicate path; no DB verification |
| src/api/auth/auth_service.py | 186 | ✅ Timing-safe login; bcrypt rounds=12 |
| src/api/dependencies.py | 42 | ✅ Proper async session management |
| src/api/security/ownership.py | 142 | ✅ Well-designed IDOR prevention factory |
| src/api/routers/events.py | 84 | 🔴 Stubbed auth; never wired |
| src/events/pipeline_executor.py | 205 | ⚠️ Mixed concrete/Protocol injection |
| src/ai/anthropic_client.py | 79 | ✅ API key sanitized; timeout enforced |
| src/ai/interfaces/i_llm_client.py | 40 | ✅ Clean Protocol definition |
| src/ai/registry/agent_registry.py | 110 | ✅ Fail-fast startup validation |
| src/ai/registry/interfaces.py | 23 | ✅ Clean Protocol |
| src/ai/tools/base.py | 307 | ✅ Well-structured ABC + caching |
| src/config/settings.py | 178 | ✅ Comprehensive; validators; 12-factor |
| src/alerts/api/alerts_router.py | 72 | ✅ Paginated; user-scoped; parameter validation |
| src/storage/repositories/base.py | 118 | ✅ Excellent tenant isolation guard |
| tests/unit/ai/test_anthropic_client.py | 117 | ✅ 4 tests cover timeout, sanitization, token forwarding |
| tests/security/test_tenant_isolation.py | 277 | ✅ 17 tests; statement inspection; cross-tenant isolation |
| docs/implr/plans/functional/PLAN-F-001.md | 539 | ✅ Comprehensive design doc |
| docs/implr/plans/functional/PLAN-F-002.md | 400 | ✅ Clear task breakdown + test specs |
| docs/implr/config/standards-card.md | 56 | ✅ Clear standards |
