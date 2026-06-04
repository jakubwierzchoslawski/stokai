---
plan_id: PLAN-F-003
slug: exposure-mapping
title: Event Exposure Mapping
linked_requirement: REQ-F-003
type: functional
status: ready
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "compute_exposure_map ≤3s; no N+1 queries; bulk fetch companies by region and sector in two round-trips maximum" }
  - { id: REQ-N-006, reason: "tenant_id scoping required on event_exposure queries; all repository methods accept and enforce tenant_id" }
dependencies:
  - { id: PLAN-F-002, reason: "geo_regions[] and affected_sectors[] on ClassificationResult must be populated before exposure can be computed; PipelineContext and ExposureCandidate types are defined there and in PLAN-F-001" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-003 — Event Exposure Mapping

## Linked Requirement
**REQ-F-003** — Event Exposure Mapping
Status: approved | Jira: —

## Objective
Implement steps 4 and 5 of the Mode A Reactive Pipeline: `compute_exposure_map` and
`persist_event_record`. Step 4 bulk-fetches all tracked companies from PostgreSQL, computes
a geo exposure weight from each company's `geo_revenue` JSONB column against the event's
`geo_regions[]`, applies a sector match against `affected_sectors[]`, merges the two weights
into a magnitude score (0.0–1.0), derives direction from event sentiment, and returns a list
of `ExposureCandidate` objects — one per company whose magnitude meets or exceeds the
configurable threshold (default 0.05). Step 5 writes the finalized `geo_event` row and all
`event_exposure` rows atomically in a single database transaction. The combined wall-clock
time for both steps must not exceed 15 seconds; step 4 alone must complete within 3 seconds
across a universe of up to 200 tracked companies. No external API calls are made by either
step.

## Architecture Context
This plan is scoped to **Layer 4 — Processing** (Architecture §4) and the `events` backend
module (Architecture §5). It also extends the `storage` module (Architecture §5) with two
new repository methods.

**Layer and module boundaries:**
- `src/events/steps/compute_exposure_map.py` — pure computation logic, no DB access; receives
  a pre-fetched list of `TrackedCompany` objects and a `ClassificationResult` and returns
  `list[ExposureCandidate]`. Follows the same step-function signature convention established
  in PLAN-F-001.
- `src/events/steps/persist_event_record.py` — delegates all DB writes to repository
  interfaces; owns the atomic transaction boundary.
- `src/storage/implementations/geo_event_repository.py` — extended with `persist_classified`
  (write the finalized `geo_event` row, including geo_regions, affected_sectors, classification
  fields).
- `src/storage/implementations/event_exposure_repository.py` — extended with `bulk_insert`
  (write all `event_exposure` rows for one event in a single transaction; accepts the
  `tenant_id` for scoping).
- `src/storage/implementations/company_repository.py` — new: `get_all_tracked(tenant_id)`
  returns all `company` rows with `is_tracked = true`, selecting only the columns needed for
  exposure computation: `company_id`, `sector_internal`, `sector_gics`, `geo_revenue`.

**Data model (Architecture §10):**
- `company.geo_revenue` JSONB — revenue breakdown by region, e.g.
  `{"US": 0.6, "Middle East": 0.3, "Europe": 0.1}`. Values must sum to ≤ 1.0; missing key
  means zero revenue from that region.
- `event_exposure(event_id, company_id) PK` — `exposure_type` enum(geo, sector, combined);
  `direction` enum(positive, negative, neutral); `magnitude` float 0.0–1.0;
  `price_change_t1d` null at creation.
- `geo_event` — receives the fully classified fields (geo_regions[], affected_sectors[],
  sentiment, cameo_code) on the `persist_classified` call.

**Multi-tenancy (Architecture §12.3):** `geo_event` carries `tenant_id = NULL` for globally
sourced events; `event_exposure` carries the requesting tenant's `tenant_id`. All
`IEventExposureRepository.bulk_insert` calls pass `tenant_id` explicitly — the repository
never infers it.

**Consumed from PLAN-F-001 (no re-implementation):**
- `src/events/models.py` — `PipelineContext`, `ClassificationResult`, `ExposureCandidate`,
  `RawEvent`
- `src/events/exceptions.py` — `PipelineError`, `StepTimeoutError`
- `src/storage/interfaces/IGeoEventRepository` — `persist_classified` method added here
- `src/storage/interfaces/IEventExposureRepository` — `bulk_insert` method added here

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-001 | `compute_exposure_map` ≤3s total; no N+1 queries | One bulk `SELECT` to fetch all tracked companies; `geo_revenue` traversal is pure Python with no extra DB round-trips; step wraps the computation in a measured block and raises `StepTimeoutError` if elapsed > 3s |
| REQ-N-006 | `tenant_id` scoping on `event_exposure` rows | `IEventExposureRepository.bulk_insert` accepts `tenant_id: UUID` as a required argument; repository implementation includes `tenant_id` in every inserted row; integration tests assert that rows for tenant A are not visible to tenant B queries |

## Component Design

### New Components

```
Module: events (src/events/)
  └── steps/
        ├── compute_exposure_map.py    — step 4: pure computation, no DB calls
        └── persist_event_record.py   — step 5: atomic geo_event + event_exposure write

Module: storage (src/storage/)
  ├── interfaces/
  │     └── ICompanyRepository         — get_all_tracked(tenant_id) → list[TrackedCompany]
  └── implementations/
        └── company_repository.py      — SQLAlchemy async implementation of ICompanyRepository

Tests:
  tests/unit/events/steps/
        ├── test_compute_exposure_map.py
        └── test_persist_event_record.py
  tests/integration/events/steps/
        └── test_exposure_mapping_integration.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/events/models.py` | Add `TrackedCompany(company_id, sector_internal, sector_gics, geo_revenue)` Pydantic model; add `ExposureResult` model (list of `ExposureCandidate` with metadata) | Step 4 needs a typed input model for company data and a typed output; PLAN-F-001 defines `ExposureCandidate` but `TrackedCompany` is new |
| `src/storage/interfaces/IGeoEventRepository` | Add `persist_classified(event_id, classification, tenant_id) → None` method to the existing interface | Step 5 needs to write the finalized geo_event fields |
| `src/storage/interfaces/IEventExposureRepository` | Add `bulk_insert(event_id, candidates, tenant_id) → int` method returning row count | Step 5 needs atomic batch write |

### Interfaces and Contracts

Exact function signatures the executor must implement.

```python
# src/events/models.py (additive changes)

class TrackedCompany(BaseModel):
    company_id: UUID
    sector_internal: str
    sector_gics: str
    geo_revenue: dict[str, float]  # {"Middle East": 0.3, "US": 0.6, ...}


# src/events/steps/compute_exposure_map.py

async def compute_exposure_map(
    ctx: PipelineContext,
    company_repo: ICompanyRepository,
    exposure_threshold: float = 0.05,
) -> PipelineContext:
    """
    Step 4 of the Mode A pipeline.

    - Calls company_repo.get_all_tracked(ctx.tenant_id) to bulk-fetch all tracked companies.
    - For each company, computes geo_weight:
        sum(geo_revenue.get(region, 0.0) for region in ctx.classification.geo_regions)
        geo_weight is clamped to [0.0, 1.0].
    - For each company, computes sector_match:
        1.0 if company.sector_internal or company.sector_gics matches any value in
        ctx.classification.affected_sectors (case-insensitive), else 0.0.
    - Computes magnitude:
        if geo_weight > 0 and sector_match > 0:  exposure_type = "combined"; magnitude = (geo_weight + sector_match) / 2
        elif geo_weight > 0:                       exposure_type = "geo";      magnitude = geo_weight
        elif sector_match > 0:                     exposure_type = "sector";   magnitude = sector_match * 0.5
        else:                                      skip company entirely.
    - Derives direction:
        sentiment > 0.1  → "positive"
        sentiment < -0.1 → "negative"
        else             → "neutral"
    - Excludes companies where magnitude < exposure_threshold.
    - Records elapsed time; raises StepTimeoutError if elapsed > 3.0s.
    - Stores list[ExposureCandidate] on ctx.exposure_candidates.
    - Returns updated ctx.
    """
    ...


# src/events/steps/persist_event_record.py

async def persist_event_record(
    ctx: PipelineContext,
    geo_event_repo: IGeoEventRepository,
    event_exposure_repo: IEventExposureRepository,
) -> PipelineContext:
    """
    Step 5 of the Mode A pipeline.

    - Opens a single database transaction.
    - Calls geo_event_repo.persist_classified(
          event_id=ctx.raw_event.event_id,
          classification=ctx.classification,
          tenant_id=ctx.tenant_id,
      ) to write the finalized geo_event row.
    - Calls event_exposure_repo.bulk_insert(
          event_id=ctx.raw_event.event_id,
          candidates=ctx.exposure_candidates,
          tenant_id=ctx.tenant_id,
      ) to write all event_exposure rows.
    - Commits both writes atomically; rolls back both on any exception and raises PipelineError.
    - Stores row_count on ctx.persisted_exposure_count.
    - Returns updated ctx.
    """
    ...


# src/storage/interfaces/i_company_repository.py

class ICompanyRepository(Protocol):
    async def get_all_tracked(self, tenant_id: UUID | None) -> list[TrackedCompany]:
        """
        Returns all company rows where is_tracked = true.
        tenant_id is accepted but companies are global (not tenant-scoped); pass None for
        global reads. Selects only: company_id, sector_internal, sector_gics, geo_revenue.
        Never returns more than 500 rows (hard guard; raises RepositoryError if exceeded).
        """
        ...


# src/storage/interfaces/i_geo_event_repository.py (additive method)

    async def persist_classified(
        self,
        event_id: UUID,
        classification: ClassificationResult,
        tenant_id: UUID | None,
    ) -> None:
        """
        Updates the geo_event row (identified by event_id) with the full classification
        fields: category, intensity, sentiment, geo_regions, affected_sectors, cameo_code.
        Raises RepositoryError if the row does not exist (raw event must have been persisted
        in step 1 by PLAN-F-001).
        """
        ...


# src/storage/interfaces/i_event_exposure_repository.py (additive method)

    async def bulk_insert(
        self,
        event_id: UUID,
        candidates: list[ExposureCandidate],
        tenant_id: UUID,
    ) -> int:
        """
        Inserts one event_exposure row per candidate in a single executemany call.
        Returns the count of rows inserted.
        Requires tenant_id on every row (REQ-N-006).
        If candidates is empty, returns 0 without error.
        """
        ...
```

## Implementation Tasks

### TASK-001: TrackedCompany Model and ExposureCandidate Tenant Fields · S/no-TDD · src/events/models.py

Add `TrackedCompany` as a Pydantic `BaseModel` to `src/events/models.py` with fields:
`company_id: UUID`, `sector_internal: str`, `sector_gics: str`,
`geo_revenue: dict[str, float]`. Validate that all `geo_revenue` float values are in
[0.0, 1.0] using `@field_validator`. If the existing `ExposureCandidate` model (from
PLAN-F-001) does not carry `direction` and `exposure_type` fields, add them now:
`direction: Literal["positive", "negative", "neutral"]`,
`exposure_type: Literal["geo", "sector", "combined"]`. Add
`persisted_exposure_count: int = 0` to `PipelineContext`. All changes are purely additive.

**AC covered**: AC-001, AC-002

---

### TASK-002: ICompanyRepository Interface · S/no-TDD · src/storage/interfaces/i_company_repository.py

Create a new `Protocol` interface `ICompanyRepository` in
`src/storage/interfaces/i_company_repository.py`. Define exactly one method:
`get_all_tracked(self, tenant_id: UUID | None) -> list[TrackedCompany]` with the contract
described in the Interfaces and Contracts section above. The interface must be importable
without any concrete implementation. Export it from `src/storage/interfaces/__init__.py`.

**AC covered**: enables AC-001, AC-002

---

### TASK-003: ICompanyRepository SQLAlchemy Implementation · S/no-TDD · src/storage/implementations/company_repository.py

Implement `CompanyRepository` as an `async` SQLAlchemy 2.0 class satisfying
`ICompanyRepository`. The `get_all_tracked` query must:
- Execute a single `SELECT company_id, sector_internal, sector_gics, geo_revenue FROM company WHERE is_tracked = true`.
- Cast `geo_revenue` JSONB to `dict[str, float]` via SQLAlchemy's `JSONB` column type.
- Raise `RepositoryError` if the result set exceeds 500 rows (guard against runaway
  universe growth).
- Return `list[TrackedCompany]`.

The `tenant_id` parameter is accepted but not used in the WHERE clause (companies are
globally tracked, not tenant-scoped). This keeps the interface symmetric with other
repositories that do filter by tenant.

**AC covered**: enables AC-001, AC-002

---

### TASK-004: IGeoEventRepository.persist_classified and IEventExposureRepository.bulk_insert Method Additions · S/no-TDD · src/storage/interfaces/i_geo_event_repository.py, src/storage/interfaces/i_event_exposure_repository.py, src/storage/implementations/geo_event_repository.py, src/storage/implementations/event_exposure_repository.py

Extend the two existing repository interfaces (defined in PLAN-F-001) with the new methods
specified in the Interfaces and Contracts section. Then implement both methods in the
corresponding SQLAlchemy classes:

`geo_event_repository.persist_classified`:
- Issues an `UPDATE geo_event SET category=:cat, intensity=:int, sentiment=:sent, geo_regions=:regions, affected_sectors=:sectors, cameo_code=:cameo WHERE event_id=:eid`.
- Raises `RepositoryError("geo_event not found")` if `rowcount == 0`.

`event_exposure_repository.bulk_insert`:
- Uses `INSERT INTO event_exposure(event_id, company_id, exposure_type, direction, magnitude, price_change_t1d, tenant_id) VALUES ...` via SQLAlchemy `executemany` with parameterized values.
- `price_change_t1d` is always `NULL` at creation.
- `tenant_id` is required; raises `ValueError` if `None` is passed (REQ-N-006 guard).
- Returns the count of rows inserted.

Both methods must be covered by the integration test in TASK-007, not here.

**AC covered**: AC-002, AC-003

---

### TASK-005: compute_exposure_map Step · M/TDD · src/events/steps/compute_exposure_map.py, tests/unit/events/steps/test_compute_exposure_map.py

Implement `compute_exposure_map` as an `async` function matching the exact signature and
algorithm described in the Interfaces and Contracts section.

Key implementation rules:
- `geo_weight` computation iterates over `ctx.classification.geo_regions`; each key lookup
  in `company.geo_revenue` is O(1) dict access — no DB calls inside the loop.
- Sector match is case-insensitive: `company.sector_internal.lower()` compared against
  each `s.lower()` in `ctx.classification.affected_sectors`.
- Both `sector_internal` and `sector_gics` are checked; a match on either counts.
- Magnitude clamped to [0.0, 1.0] before threshold check.
- Elapsed time measured via `time.monotonic()` wrapping the entire computation loop;
  raises `StepTimeoutError("compute_exposure_map exceeded 3.0s")` if elapsed > 3.0.
- Stores results on `ctx.exposure_candidates: list[ExposureCandidate]`.

**Tests to write first (TDD)**:
- Company with geo_revenue `{"Middle East": 0.3}` and event geo_regions `["Middle East"]`
  produces `ExposureCandidate` with exposure_type="geo" and magnitude=0.3 > threshold
- Company with geo_revenue `{"US": 1.0}` and event geo_regions `["Middle East"]` produces
  no `ExposureCandidate` (no geo match, no sector match)
- Company with sector_internal="energy" and affected_sectors=["energy"] produces
  `ExposureCandidate` with exposure_type="sector" and magnitude=0.5
- Company matching both geo and sector produces exposure_type="combined" and
  magnitude=(geo_weight + 1.0) / 2
- Company with magnitude=0.03 (below default threshold 0.05) is excluded from results
- Event sentiment=0.5 produces direction="positive"; sentiment=-0.5 produces
  direction="negative"; sentiment=0.0 produces direction="neutral"
- Case-insensitive sector matching: company.sector_internal="Energy" matches
  affected_sectors=["energy"]
- sector_gics match also triggers sector exposure when sector_internal does not match
- When elapsed time exceeds 3.0s (simulated via monkeypatching `time.monotonic`),
  `StepTimeoutError` is raised
- Empty affected_sectors[] and empty geo_regions[] on the event produces no candidates
  (all companies below threshold)
- geo_revenue key missing from JSONB is treated as 0.0 weight

**AC covered**: AC-001, AC-002, AC-004

---

### TASK-006: persist_event_record Step · M/TDD · src/events/steps/persist_event_record.py, tests/unit/events/steps/test_persist_event_record.py

Implement `persist_event_record` as an `async` function matching the signature in the
Interfaces and Contracts section. The function wraps both repository calls in an `async`
SQLAlchemy `begin()` context manager so that a failure in either write rolls back both.

Implementation details:
- If `ctx.exposure_candidates` is empty, `bulk_insert` is still called (returns 0; no error).
- If `geo_event_repo.persist_classified` raises `RepositoryError`, the transaction is rolled
  back and `PipelineError("persist_event_record: geo_event write failed")` is raised —
  never propagating raw DB error details.
- If `event_exposure_repo.bulk_insert` raises any exception, the same rollback-and-wrap
  pattern applies.
- Sets `ctx.persisted_exposure_count = row_count` before returning.

**Tests to write first (TDD)**:
- Both repository methods called with correct arguments when `ctx.exposure_candidates` is
  non-empty; `ctx.persisted_exposure_count` equals the row count returned by `bulk_insert`
- When `ctx.exposure_candidates` is empty, `bulk_insert` is still called with an empty list
  and no exception is raised; `ctx.persisted_exposure_count == 0`
- When `persist_classified` raises `RepositoryError`, a `PipelineError` is raised and
  `bulk_insert` is not called (assert mock was not called)
- When `bulk_insert` raises an exception, a `PipelineError` is raised; assert that the
  overall transaction was rolled back (mock DB session `rollback` called)
- `tenant_id` from `ctx` is passed to `bulk_insert` without modification (REQ-N-006 check)
- Returned `ctx.persisted_exposure_count` matches the integer returned by the mocked
  `bulk_insert`

**AC covered**: AC-002, AC-003

---

### TASK-007: Integration Test — Exposure Mapping End-to-End · M/TDD · tests/integration/events/steps/test_exposure_mapping_integration.py

Write an integration test suite exercising steps 4 and 5 together against a real test
database (SQLite in-memory or PostgreSQL test fixture, following the project's integration
test pattern). All LLM calls are absent from this plan; only DB operations are tested.

**Tests to write first (TDD)**:
- Seed two tracked companies — one with `geo_revenue={"Middle East": 0.4}` and
  `sector_internal="energy"`, one with `geo_revenue={"US": 0.9}` and
  `sector_internal="finance"`. Run `compute_exposure_map` with
  `geo_regions=["Middle East"]` and `affected_sectors=["energy"]`. Assert only the first
  company appears in `ctx.exposure_candidates`.
- Run `persist_event_record` after the above; assert exactly one `event_exposure` row
  exists in the DB for the correct company with `tenant_id` matching the test tenant.
- Run `persist_event_record` with two candidates; assert exactly two `event_exposure` rows
  are committed and the `geo_event` row has been updated with classification fields.
- Simulate `persist_classified` DB failure (drop the `geo_event` table after seeding);
  assert no `event_exposure` rows are written (transaction atomicity — AC-003).
- Attempt to query `event_exposure` rows using a different `tenant_id`; assert zero rows
  returned (REQ-N-006 tenant isolation).
- With 200 seeded companies (boundary of tracked universe), assert `compute_exposure_map`
  completes in < 3.0s real wall time (performance guard — AC-004).

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

## Acceptance Criteria Coverage

- AC-001: Given a classified event with geo_regions=["Middle East"] and affected_sectors=["energy"], companies with geo_revenue JSONB containing "Middle East" > 0 and sector matching "energy" receive event_exposure rows with magnitude > 0 and appropriate exposure_type → TASK-001, TASK-005, TASK-007
- AC-002: Given a company with zero revenue in the event's geo_regions and no sector match, no event_exposure row is created for that company → TASK-001, TASK-005, TASK-006, TASK-007
- AC-003: Given the event is persisted (step 5), the geo_event row and all event_exposure rows are committed in a single atomic transaction; partial writes are not permitted → TASK-004, TASK-006, TASK-007
- AC-004: Given the full tracked company universe (~200 companies), the exposure computation and DB write complete within the 15-second stage-gate budget allocated to steps 4–5 → TASK-005, TASK-007

## Risks and Notes

- **JSONB key normalisation:** `geo_revenue` keys are free-form strings (e.g. "Middle East",
  "Middle east", "middle_east"). The event classifier (PLAN-F-002) produces `geo_regions`
  from a Haiku prompt and may not normalise casing identically to how companies were seeded.
  The `compute_exposure_map` algorithm uses case-sensitive dict lookup by default. For MVP,
  document that `geo_revenue` keys and classifier region outputs must use a shared controlled
  vocabulary. A future hardening task should add a normalisation layer. Log a WARNING in
  `compute_exposure_map` if no companies match any geo_region (possible normalisation gap).

- **Magnitude formula extensibility:** The current formula `(geo_weight + sector_match) / 2`
  for "combined" exposure is intentionally simple. The architecture's scoring engine
  (PLAN-F-017) will later apply a geo-modifier to company scores; that geo-modifier is not
  the same as exposure magnitude here. These are two separate computations. Do not conflate
  them. The magnitude formula is isolated in `compute_exposure_map.py` so it can be replaced
  without touching the persistence step.

- **Sector match vocabulary gap:** `sector_internal` and `sector_gics` may use different
  taxonomies than what the event classifier produces in `affected_sectors`. For MVP, a
  case-insensitive substring match (`"energy" in sector_gics.lower()`) is acceptable.
  A configurable sector-synonym map in settings (e.g. `{"oil & gas": ["energy"]}`) should
  be added before production rollout.

- **Empty exposure_candidates is valid:** If no company passes the threshold, the pipeline
  continues normally — `persist_event_record` writes the `geo_event` row (classification
  fields) and zero `event_exposure` rows. The downstream alert step (PLAN-F-005) must handle
  this case gracefully. Do not raise an error when `exposure_candidates` is empty.

- **Transaction boundary ownership:** Steps 4 and 5 are intentionally split. Step 4 is pure
  Python computation (no I/O after the single bulk fetch). Step 5 owns the only write
  transaction. This split makes step 4 fully unit-testable without a DB fixture and keeps
  the transaction as short as possible (reduces lock contention during high-volume ingestion).

- **REQ-N-006 enforcement:** The `tenant_id` guard in `bulk_insert` (raises `ValueError` if
  `None` is passed) is a hard defence. However, `geo_event` rows may legitimately carry
  `tenant_id = NULL` for global events (Architecture §12.3). The guard applies only to
  `event_exposure`, where tenant isolation is required. Ensure this distinction is clear in
  code comments.
