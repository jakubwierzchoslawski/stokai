---
plan_id: PLAN-F-018
slug: portfolio-scoring-and-geo-modifier
title: Portfolio Scoring and Real-Time Geo-Modifier
linked_requirement: REQ-F-018
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "Geo-modifier targeted update (UPDATE WHERE company_id IN (...)) must complete within 5 seconds for up to 200 companies; no N+1 queries" }
dependencies:
  - { id: PLAN-F-017, reason: "ICompanyScoreRepository, CompanyScoreRecord, and GeoModifier from scoring engine are consumed directly; base score infrastructure must exist" }
  - { id: PLAN-F-003, reason: "IEventExposureRepository.get_by_event provides the event_exposure rows; event_exposure table and bulk_insert must exist" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-04T00:00:00Z
---

# PLAN-F-018 — Portfolio Scoring and Real-Time Geo-Modifier

## Linked Requirement
**REQ-F-018** — Portfolio Scoring and Real-Time Geo-Modifier
Status: approved | Jira:

## Objective

Build the real-time geo-modifier pathway that updates `company_score.geo_adjusted` for all
companies exposed to a newly persisted geopolitical event, then broadcasts the score changes
to subscribed map clients via WebSocket — all without triggering a full DSL formula
recalculation. The plan delivers: a `GeoModifierWorker` Celery task that reads
`event_exposure` rows and applies the formula
`geo_adjusted = base_score × (1 + geo_weight × magnitude × direction_sign)`;
a bulk-update repository method that writes only the `geo_adjusted` column in a single
parameterized `UPDATE ... WHERE company_id IN (...)` statement; a new `GeoModifierPayload`
WebSocket message type that carries per-company score deltas; and an API endpoint that
allows the scoring profile's `geo_weight` values to be reapplied to existing exposures
without requiring a new event. Score updates must reach the map within 5 seconds of the
event being persisted (AC-001), and companies outside the exposure set are never touched
(AC-003).

## Architecture Context

This plan lives entirely in **Layer 4 — Processing** (`scoring` module) and **Layer 5 —
Serving** (`api` module, WebSocket manager). It consumes Layer 3 (Storage) through the
repository pattern only.

**Dependency chain:** Mode A step 5 (`persist_event_record`, PLAN-F-003) writes
`event_exposure` rows and then publishes a `score_invalidation` message to the Celery
queue (previously wired in PLAN-F-017 TASK-009). This plan adds a second, distinct Celery
task — `scoring.apply_geo_modifier` — that runs in parallel (or immediately after) the
full-rescore task but performs only the targeted `geo_adjusted` write. The two tasks are
independent: the geo-modifier task does not wait for the full-rescore task to complete.

**Data entities (ARCHITECTURE.md §10):**
- `company_score`: PK `(company_id, indicator_id, computed_at)` TimescaleDB hypertable;
  `score` column holds the base DSL-evaluated value; `geo_adjusted` column is the target
  of this plan's writes. D4 event-driven snapshot rule applies: a new row is written only
  when `geo_adjusted` changes.
- `event_exposure(event_id, company_id)`: `magnitude` float 0–1, `direction` enum
  (positive/negative/neutral) — both consumed as inputs to the geo-modifier formula.
- `indicator`: `geo_weight` float — the weight applied per indicator in the formula.

**WebSocket (ARCHITECTURE.md §13):** The existing WebSocket manager in `src/api/` already
handles real-time event delivery. This plan adds a new message type `geo_modifier_update`
carrying a `GeoModifierPayload`; the WebSocket layer is extended, not replaced.

**PLAN-F-017 contract reuse:** `ICompanyScoreRepository` (defined in PLAN-F-017) already
exposes `get_current(company_id, indicator_id)` and `upsert_if_changed(record)`. This plan
adds one new method `bulk_update_geo_adjusted(updates)` to that interface, leaving all
other methods untouched.

**Performance constraint (ARCHITECTURE.md §9 / AC-001):** The targeted UPDATE must use a
single SQL statement `UPDATE company_score SET geo_adjusted = <case expression> WHERE
company_id IN (...)` rather than per-row updates. For up to 200 companies × N indicators,
the total write round-trips must be O(indicators), not O(companies × indicators).

## Component Design

### New Components

```
Module: scoring  (src/scoring/)
  ├── geo_modifier_worker.py     — Celery task: apply_geo_modifier
  │                                 Reads event_exposure rows, loads base scores and
  │                                 indicator geo_weights, applies formula, bulk-writes
  │                                 geo_adjusted, triggers WebSocket broadcast
  └── schemas/
      └── geo_modifier.py        — GeoModifierPayload Pydantic schema (WebSocket DTO)

Module: storage  (src/storage/)
  └── interfaces/
      └── i_event_exposure_repository.py  (additive method: get_by_event)

Module: api  (src/api/)
  └── v1/
      └── scoring/
          └── geo_modifier.py    — REST endpoint: POST /api/v1/scoring/geo-modifier/reapply
                                   Accepts {event_id, profile_id}; re-triggers the
                                   geo-modifier Celery task for a previously processed event
                                   using the current profile's geo_weight values (AC-005)

Tests:
  tests/unit/scoring/
      ├── test_geo_modifier_worker.py
      └── test_geo_modifier_formula.py
  tests/integration/scoring/
      └── test_geo_modifier_integration.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/scoring/repositories/interfaces.py` | Add `bulk_update_geo_adjusted(updates: list[GeoAdjustedUpdate]) -> int` to `ICompanyScoreRepository` | Targeted bulk write without full row replacement (AC-001, AC-003 selectivity) |
| `src/scoring/repositories/company_score_repo.py` | Implement `bulk_update_geo_adjusted` as a single `UPDATE ... SET geo_adjusted = CASE WHEN ... END WHERE company_id IN (...)` using SQLAlchemy Core | Avoid N+1; meet the 5-second SLA |
| `src/storage/interfaces/i_event_exposure_repository.py` | Add `get_by_event(event_id: UUID, tenant_id: UUID) -> list[ExposureRow]` method | Geo-modifier worker needs to load exposures by event |
| `src/storage/implementations/event_exposure_repository.py` | Implement `get_by_event` — single SELECT with `event_id` and `tenant_id` in WHERE clause | Provide the exposure rows to the Celery task |
| `src/api/websocket_manager.py` (or equivalent) | Register handler for `geo_modifier_update` message type; add `broadcast_geo_modifier(payload: GeoModifierPayload)` method | Propagate score changes to subscribed map clients (AC-002) |
| `src/config/celery_app.py` | Register `scoring.apply_geo_modifier` task | Wire Celery task |
| `src/events/steps/persist_event_record.py` | After `event_exposure_repo.bulk_insert` commits, enqueue `scoring.apply_geo_modifier.delay(event_id=..., tenant_id=...)` | Trigger geo-modifier after exposure rows are available |

### Interfaces and Contracts

```python
# src/scoring/schemas/geo_modifier.py

from pydantic import BaseModel
from uuid import UUID

class CompanyScoreDelta(BaseModel):
    company_id: UUID
    ticker: str
    new_geo_adjusted: float
    score_delta: float          # new_geo_adjusted - previous_geo_adjusted

class GeoModifierPayload(BaseModel):
    event_id: UUID
    affected_companies: list[CompanyScoreDelta]


# Additive to src/scoring/repositories/interfaces.py

from dataclasses import dataclass

@dataclass(frozen=True)
class GeoAdjustedUpdate:
    company_id: UUID
    indicator_id: UUID
    geo_adjusted: float
    computed_at: datetime        # timestamp of the new snapshot row

class ICompanyScoreRepository(Protocol):
    # ... existing methods from PLAN-F-017 unchanged ...

    async def bulk_update_geo_adjusted(
        self, updates: list[GeoAdjustedUpdate]
    ) -> int:
        """
        Writes geo_adjusted values for multiple (company_id, indicator_id) pairs.
        Inserts a new company_score row for each update (event-driven snapshot, D4),
        carrying the existing score/raw_value/percentile/inputs_hash from the most recent
        row but with the new geo_adjusted value.
        Returns the count of rows written.
        Only writes a row when geo_adjusted differs from the current row's geo_adjusted
        by more than SCORE_CHANGE_EPSILON (0.001) — consistent with upsert_if_changed.
        """
        ...


# Additive to src/storage/interfaces/i_event_exposure_repository.py

from dataclasses import dataclass

@dataclass(frozen=True)
class ExposureRow:
    company_id: UUID
    exposure_type: str          # "geo" | "sector" | "combined"
    direction: str              # "positive" | "negative" | "neutral"
    magnitude: float            # 0.0–1.0

class IEventExposureRepository(Protocol):
    # ... existing methods from PLAN-F-003 unchanged ...

    async def get_by_event(
        self, event_id: UUID, tenant_id: UUID
    ) -> list[ExposureRow]:
        """
        Returns all event_exposure rows for the given event_id scoped to tenant_id.
        Returns an empty list (never raises) when no rows exist.
        """
        ...


# src/scoring/geo_modifier_worker.py — task signature

from celery import shared_task

@shared_task(name="scoring.apply_geo_modifier", bind=True, max_retries=3)
async def apply_geo_modifier(
    self,
    event_id: str,
    tenant_id: str,
) -> dict:
    """
    1. Load event_exposure rows via IEventExposureRepository.get_by_event
    2. If no rows: log INFO and return early (AC-003 — no-op on empty exposure)
    3. Load all active indicators for the tenant via IIndicatorRepository.list_by_tenant
    4. For each indicator with geo_weight > 0:
       a. Load current company_score rows for affected companies in one query
          (SELECT WHERE company_id IN (...) AND indicator_id = :indicator_id)
       b. For each (company_id, exposure_row):
          direction_sign = +1 if direction == "positive" else -1
          geo_adjusted = base_score × (1 + geo_weight × magnitude × direction_sign)
          geo_adjusted = clamp(geo_adjusted, 0.0, 100.0)
    5. Call ICompanyScoreRepository.bulk_update_geo_adjusted(updates)
    6. Collect CompanyScoreDelta list; broadcast GeoModifierPayload via WebSocket
    7. Return {"event_id": event_id, "companies_updated": count}
    """
    ...
```

## Implementation Tasks

### TASK-001: GeoModifierPayload schema and ExposureRow dataclass · S/no-TDD · src/scoring/schemas/geo_modifier.py,src/storage/interfaces/i_event_exposure_repository.py

Define the `GeoModifierPayload` and `CompanyScoreDelta` Pydantic models in
`src/scoring/schemas/geo_modifier.py`. Add the `ExposureRow` frozen dataclass to
`src/storage/interfaces/i_event_exposure_repository.py`. Both are pure data definitions
with no logic.

Export `GeoModifierPayload` from `src/scoring/schemas/__init__.py` and `ExposureRow` from
`src/storage/interfaces/__init__.py`.

**AC covered**: AC-002 (WebSocket DTO structure), AC-001 (type foundation for the worker)

---

### TASK-002: IEventExposureRepository.get_by_event — interface and implementation · S/no-TDD · src/storage/interfaces/i_event_exposure_repository.py,src/storage/implementations/event_exposure_repository.py

Add `get_by_event(event_id: UUID, tenant_id: UUID) -> list[ExposureRow]` to the
`IEventExposureRepository` Protocol (additive; no existing methods change). Implement it
in `EventExposureRepository` using a single SQLAlchemy 2.0 async SELECT:

```sql
SELECT company_id, exposure_type, direction, magnitude
FROM event_exposure
WHERE event_id = :event_id AND tenant_id = :tenant_id
```

Map each row to an `ExposureRow` dataclass. Return `[]` on empty result. Never filter by
additional columns — direction and magnitude are passed through as-is.

**AC covered**: enables AC-001, AC-003 (event-scoped fetch is the selectivity gate)

---

### TASK-003: ICompanyScoreRepository.bulk_update_geo_adjusted — interface and implementation · M/TDD · src/scoring/repositories/interfaces.py,src/scoring/repositories/company_score_repo.py,tests/unit/scoring/test_bulk_update_geo_adjusted.py

Add `GeoAdjustedUpdate` dataclass and `bulk_update_geo_adjusted` method signature to
`ICompanyScoreRepository` in `src/scoring/repositories/interfaces.py`.

Implement `bulk_update_geo_adjusted` in `CompanyScoreRepository`. The implementation must:
- Group updates by `indicator_id` to execute one INSERT batch per indicator (not per company).
- For each indicator group: fetch the most recent `company_score` row for each
  `company_id` in the group (single SELECT with `WHERE company_id = ANY(:ids) AND
  indicator_id = :indicator_id ORDER BY computed_at DESC`), then build INSERT rows
  carrying `score`, `raw_value`, `percentile`, and `inputs_hash` from the latest row but
  with the new `geo_adjusted` and a fresh `computed_at = now()`.
- Apply the epsilon guard: skip a company/indicator pair if
  `abs(new_geo_adjusted - current_geo_adjusted) <= 0.001`.
- Execute all inserts via a single `INSERT INTO company_score (...) VALUES ...`
  executemany within the same async transaction.
- Return the count of rows actually inserted (after epsilon filtering).

**Tests to write first (TDD):**
- `bulk_update_geo_adjusted([GeoAdjustedUpdate(company_id=A, indicator_id=I, geo_adjusted=72.5, ...)])` with a current `geo_adjusted=50.0` for (A, I) → inserts one new row, returns 1
- `bulk_update_geo_adjusted` with two companies sharing the same `indicator_id` → executes exactly one SELECT query per indicator_id group (assert via query count)
- `bulk_update_geo_adjusted` where new `geo_adjusted` is within 0.001 of the current value → returns 0, no row inserted
- `bulk_update_geo_adjusted([])` → returns 0, no DB interaction
- Returned `computed_at` on each new row is strictly greater than the previous row's `computed_at` (snapshot integrity)

**AC covered**: AC-001 (bulk write), AC-003 (epsilon guard; no writes for unchanged values)

---

### TASK-004: WebSocket broadcast for geo-modifier updates · M/TDD · src/api/websocket_manager.py,tests/unit/api/test_websocket_geo_modifier.py

Extend the existing WebSocket manager with a `broadcast_geo_modifier` coroutine that
accepts a `GeoModifierPayload` and publishes a message of type `geo_modifier_update` to
all currently subscribed map clients.

Message envelope (sent to client):
```json
{
  "type": "geo_modifier_update",
  "payload": {
    "event_id": "<uuid>",
    "affected_companies": [
      {"company_id": "<uuid>", "ticker": "AAPL", "new_geo_adjusted": 72.5, "score_delta": -7.5}
    ]
  }
}
```

The method must use `asyncio.gather` to fan-out sends to all subscribed connections.
If a connection is closed during send, catch `WebSocketDisconnect` and remove that
connection from the active set without failing the broadcast.

**Tests to write first (TDD):**
- `broadcast_geo_modifier(payload)` with two active subscribers → both receive a message with `type == "geo_modifier_update"` (assert on mock send calls)
- `broadcast_geo_modifier(payload)` with one subscriber that raises `WebSocketDisconnect` → the other subscriber still receives the message; the disconnected one is removed from the active set
- `broadcast_geo_modifier(payload)` with zero subscribers → completes immediately without error
- The serialized `payload` in the message matches `GeoModifierPayload.model_dump(mode="json")`

**AC covered**: AC-002 (WebSocket delivery to map clients)

---

### TASK-005: GeoModifierWorker Celery task · M/TDD · src/scoring/geo_modifier_worker.py,src/config/celery_app.py,tests/unit/scoring/test_geo_modifier_worker.py

Implement the `apply_geo_modifier` Celery task following the algorithm in the Interfaces
and Contracts section. Register it in `src/config/celery_app.py` as
`"scoring.apply_geo_modifier"`.

The task constructor accepts injected repository instances via a dependency-injection
pattern compatible with Celery (class-based task with `__init__` receiving repository
factories, or a module-level factory function resolving repositories from app context).
Direct `new ConcreteClass()` calls inside the task body are prohibited (SOLID DI rule).

Key constraints:
- Load all indicators in one `IIndicatorRepository.list_by_tenant(tenant_id)` call; filter
  `geo_weight > 0` in Python (not DB) to avoid a second query.
- For each indicator: load base scores in one SELECT (not per-company), build updates,
  call `bulk_update_geo_adjusted` — total DB round-trips per event = O(indicators_with_geo_weight + 1).
- Use `direction_sign = +1 if exposure.direction == "positive" else -1`; `"neutral"`
  direction maps to `direction_sign = 0` (net zero geo effect).
- Clamp `geo_adjusted` to `[0.0, 100.0]` before writing.
- After all writes, collect tickers for affected companies (one SELECT from `company` by
  `company_id IN (...)`) and build `GeoModifierPayload`.
- Call `await websocket_manager.broadcast_geo_modifier(payload)`.
- On Celery retry (max 3), the task is idempotent: re-running for the same `event_id`
  re-computes and re-writes, which is safe because `bulk_update_geo_adjusted` applies the
  epsilon guard.

**Tests to write first (TDD):**
- Happy path: given two exposure rows (company A: magnitude=0.4, direction=positive; company B: magnitude=0.2, direction=negative) and one indicator with geo_weight=0.5, base_score=80.0 for both → A gets `geo_adjusted = 80 × (1 + 0.5 × 0.4 × 1) = 96.0`; B gets `80 × (1 + 0.5 × 0.2 × -1) = 72.0`
- Given `get_by_event` returns empty list → `bulk_update_geo_adjusted` is never called; `broadcast_geo_modifier` is never called; task returns `{"companies_updated": 0}`
- Given all indicators have `geo_weight == 0` → no updates, no broadcast
- Given company has no current `company_score` row for an indicator → that company/indicator pair is skipped (no KeyError; logged at WARNING level)
- `broadcast_geo_modifier` is called exactly once after all `bulk_update_geo_adjusted` calls complete; the payload's `affected_companies` list matches the computed deltas
- Retry idempotency: calling the task twice with the same `event_id` and identical inputs produces the same final `geo_adjusted` values (no phantom accumulation)

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

### TASK-006: Trigger geo-modifier from persist_event_record · S/no-TDD · src/events/steps/persist_event_record.py

After the atomic transaction in `persist_event_record` commits successfully (both
`persist_classified` and `bulk_insert` have completed), enqueue the geo-modifier Celery
task:

```python
from src.scoring.geo_modifier_worker import apply_geo_modifier

apply_geo_modifier.delay(
    event_id=str(ctx.raw_event.event_id),
    tenant_id=str(ctx.tenant_id),
)
```

The enqueue call is placed after the `async with session.begin()` block exits — never
inside the transaction — so a Celery broker failure does not roll back the DB writes.
The task is fire-and-forget; `persist_event_record` does not await its result.

Add `geo_modifier_enqueued: bool = False` to `PipelineContext` (additive field, default
False) and set it to `True` after a successful enqueue. This field supports observability
and testing assertions.

**AC covered**: AC-001 (triggers the 5-second clock), enables AC-002, AC-003

---

### TASK-007: REST endpoint — reapply geo-modifier with current profile · M/TDD · src/api/v1/scoring/geo_modifier.py,tests/integration/api/scoring/test_geo_modifier_api.py

Implement `POST /api/v1/scoring/geo-modifier/reapply` with request body:
```json
{"event_id": "<uuid>", "profile_id": "<uuid>"}
```

The endpoint:
1. Validates that the `event_id` exists and has `event_exposure` rows (returns `404` if not).
2. Validates that `profile_id` belongs to the calling user's tenant (returns `403` if not).
3. Enqueues `apply_geo_modifier.delay(event_id=..., tenant_id=...)` — the task loads the
   current indicator `geo_weight` values from DB at execution time, so passing the
   profile is not needed in the task signature; this endpoint validates ownership only.
4. Returns `202 Accepted` with body `{"task_queued": true, "event_id": "<uuid>"}`.

Authentication: requires valid JWT. Authorization: `end_user`, `operator`, and `admin`
roles are all permitted (not admin-only).

**Tests to write first (TDD):**
- `POST /api/v1/scoring/geo-modifier/reapply` with valid JWT and existing `event_id` → 202, task enqueued (assert `apply_geo_modifier.delay` called with correct args via mock)
- Same endpoint with `event_id` that has no `event_exposure` rows → 404 with error envelope
- Same endpoint with `profile_id` belonging to a different tenant → 403
- Same endpoint without JWT → 401
- Same endpoint with `event_id` as non-UUID string → 422 (Pydantic validation)

**AC covered**: AC-005

---

### TASK-008: DB migration — add geo_modifier_enqueued to pipeline context; no schema changes needed for company_score · S/no-TDD · src/db/migrations/versions/018_geo_modifier.py

The `company_score` table already has the `geo_adjusted` column (created in PLAN-F-017
TASK-015). This migration is minimal — it adds a partial index to accelerate the
geo-modifier read pattern:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_score_geo_lookup
ON company_score (indicator_id, company_id, computed_at DESC)
WHERE geo_adjusted IS NOT NULL;
```

This index supports the `SELECT ... WHERE company_id = ANY(:ids) AND indicator_id = :id
ORDER BY computed_at DESC` query in `bulk_update_geo_adjusted`.

No new tables are introduced. The `event_exposure` `direction` and `magnitude` columns
already exist from PLAN-F-003.

**AC covered**: AC-001 (index enables sub-5-second SLA at 200 companies)

---

### TASK-009: Integration test — geo-modifier end-to-end · M/TDD · tests/integration/scoring/test_geo_modifier_integration.py

Write an integration test suite that exercises the full geo-modifier flow against a real
test database.

**Tests to write first (TDD):**
- Seed one `geo_event`, two `event_exposure` rows (company A: magnitude=0.6, direction=positive; company B: magnitude=0.3, direction=negative), one indicator with geo_weight=0.8, base scores of 70.0 for both. Run `apply_geo_modifier` synchronously (bypass Celery in tests via direct function call). Assert `company_score` rows for A and B have `geo_adjusted != 70.0`; assert company C (not in exposure) has no new row.
- Assert `geo_adjusted` for company A equals `70.0 × (1 + 0.8 × 0.6 × 1) = 103.6` → clamped to 100.0 (boundary test).
- Assert `geo_adjusted` for company B equals `70.0 × (1 + 0.8 × 0.3 × -1) = 70.0 × 0.76 = 53.2`.
- Assert that with `event_intensity = 5` vs `event_intensity = 1` the `score_delta` on the `GeoModifierPayload` is measurably larger (AC-004 proxy via magnitude difference; intensity is encoded in the exposure `magnitude` produced by PLAN-F-003).
- Re-running the task for the same event with the same inputs → no new rows written (epsilon guard); `bulk_update_geo_adjusted` returns 0.
- Assert total wall time for 200 companies × 1 indicator completes in < 5 seconds.

**AC covered**: AC-001, AC-002 (payload shape asserted), AC-003, AC-004, AC-005 (reapply verified via direct task call)

---

## Acceptance Criteria Coverage

- AC-001: company_score.geo_adjusted updated for all exposed companies within 5 seconds, without DSL recalculation → TASK-005, TASK-006, TASK-008, TASK-009
- AC-002: WebSocket message sent with updated score values for affected companies, causing map marker colors to update → TASK-001, TASK-004, TASK-005, TASK-009
- AC-003: Companies not in event_exposure set are not touched → TASK-002, TASK-003, TASK-005, TASK-009
- AC-004: Geo-adjusted score change is measurably larger for intensity-5 events than intensity-1 events → TASK-005, TASK-009
- AC-005: Scoring profile change triggers geo-modifier reapplication using new geo_weight values without requiring a new event → TASK-007, TASK-009

## Acceptance Notes

AC-004 is verified indirectly: event intensity is encoded into `event_exposure.magnitude`
by PLAN-F-003's `compute_exposure_map` step (higher intensity events produce higher
magnitude values for the same geographic revenue fraction). The integration test validates
the AC by asserting that a magnitude=0.8 exposure produces a larger `score_delta` than a
magnitude=0.16 exposure, corresponding to intensity-5 vs intensity-1 events where
geo_revenue fraction is constant.

AC-005 reapplication does not require the caller to pass geo_weight values explicitly. The
`apply_geo_modifier` task always loads the current `indicator.geo_weight` from the database
at task execution time. This means that after a scoring profile update, calling the reapply
endpoint re-runs the task which reads the updated weights automatically.

## Risks and Notes

- **Neutral direction produces zero geo effect:** `direction == "neutral"` maps to
  `direction_sign = 0`, so `geo_adjusted == base_score` for neutral exposures. This is
  correct behaviour but may be surprising to users who see companies in the exposure set
  with no apparent score change. Log at DEBUG level when neutral direction causes a no-op.

- **Race condition between full-rescore and geo-modifier tasks:** PLAN-F-017 TASK-009
  (`scoring.invalidate_and_rescore`) and this plan's `scoring.apply_geo_modifier` are both
  triggered after `persist_event_record`. If the full rescore completes and writes new
  `company_score` rows while the geo-modifier is reading base scores, the geo-modifier may
  read stale `score` values. This is acceptable for MVP: the geo-modifier reads the latest
  row by `ORDER BY computed_at DESC LIMIT 1`, so it will pick up the post-rescore base score
  if the rescore completed first, or the pre-rescore base score otherwise. A second run of
  the geo-modifier via the reapply endpoint resolves any race. Flag for Phase 2
  hardening via a task-chaining dependency.

- **Missing base score rows:** If `company_score` has no row for a `(company_id,
  indicator_id)` pair (e.g., the indicator was added after the company's last full score
  run), the geo-modifier silently skips that pair. Log a WARNING per skipped pair to aid
  debugging. A full rescore (PLAN-F-017) must run first to seed the base row.

- **TimescaleDB chunk boundary:** `bulk_update_geo_adjusted` uses INSERT (not UPDATE)
  because `company_score` is a TimescaleDB hypertable with `computed_at` as the partition
  key. True UPDATE on older chunks is unsupported by TimescaleDB without disabling
  compression. Always INSERT a new snapshot row; never UPDATE an existing one.

- **Ticker lookup cost:** `broadcast_geo_modifier` requires tickers for the
  `CompanyScoreDelta` payload. Fetch tickers in a single `SELECT company_id, ticker FROM
  company WHERE company_id = ANY(:ids)` call after all score writes complete. Do not join
  the ticker fetch into the score write query (keeps write path simple).

- **WebSocket broadcast is best-effort:** If the WebSocket manager has zero active
  subscribers (e.g., no browser tabs open), the broadcast completes immediately with no
  side effects. Map clients that reconnect after the event will receive current
  `geo_adjusted` values from the REST score endpoint — there is no replayable event stream
  in MVP.
