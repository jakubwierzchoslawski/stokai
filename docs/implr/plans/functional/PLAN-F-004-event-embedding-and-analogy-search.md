---
plan_id: PLAN-F-004
slug: event-embedding-and-analogy-search
title: Event Embedding and Historical Analogy Search
linked_requirement: REQ-F-004
type: functional
status: done
executed_at: 2026-06-03T00:00:00Z
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "embed_event step ≤ 2 s; find_historical_analogies step ≤ 3 s" }
  - { id: REQ-N-008, reason: "embedding API call logged as Langfuse span with token count and cost" }
dependencies:
  - { id: PLAN-F-031, reason: "HNSW index requires historical event embeddings from cold-start seeding before analogy search returns meaningful results" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-004 — Event Embedding and Historical Analogy Search

## Linked Requirement
**REQ-F-004** — Event Embedding and Historical Analogy Search
Status: approved | Jira: —

## Objective
Implement Mode A pipeline steps 6 and 7 as independently testable units within the `events`
module, backed by a protocol-driven `EmbeddingService` in the `ai` module. Step 6
(`embed_event`) calls OpenAI text-embedding-3-small with up to 500 tokens of event text,
receives a VECTOR(1536) response, persists the embedding to the `event_embedding` table via
the `storage` module's repository, and completes within 2 seconds. Step 7
(`find_historical_analogies`) executes a pgvector HNSW cosine top-K search over the
`event_embedding` table, joins against `event_exposure` to retrieve `price_change_t1d`
outcome statistics, computes `sample_size`, sets the `low_sample` flag when fewer than 5
valid outcomes exist, and completes within 3 seconds. The HNSW index (`vector_cosine_ops`)
must exist on the table before step 7 is useful; that index is created by the cold-start
seeding migration (PLAN-F-031). Every embedding API call is recorded as a Langfuse child span
carrying token count and cost (REQ-N-008). Embeddings are persisted with no expiry (infinite
TTL) and are not re-fetched from the API once stored.

## Architecture Context
This plan operates at Layer 3 (Storage) and Layer 4 (Processing) of the six-layer model
(Architecture §4), and touches the `ai`, `events`, and `storage` modules (Architecture §5).

**Module ownership:**
- `src/ai/embedding/` — `EmbeddingService` protocol and `OpenAIEmbeddingService` adapter.
  The `ai` module is the only place that touches the OpenAI embeddings API, consistent with
  Principle 1 (everything behind an interface) and Architecture §5 which states the `ai`
  module owns LLM and embedding provider integrations.
- `src/events/steps/` — `embed_event` (step 6) and `find_historical_analogies` (step 7)
  implementations; these are step functions consumed by `PipelineExecutor` from PLAN-F-001.
- `src/storage/repositories/` — `EventEmbeddingRepository` interface and its SQLAlchemy
  implementation, performing all SQL against `event_embedding` and the join to
  `event_exposure`.

**Data model** (Architecture §10):
```
event_embedding (event_id PK FK→geo_event, embedding VECTOR(1536), created_at)
  HNSW index (vector_cosine_ops)  ← created by PLAN-F-031 migration
```
The `AnalogSearchResult` Pydantic model carries `event_id`, `similarity_score`,
`event_title`, `event_date`, `intensity`, `category`, `price_change_t1d`, `sample_size`, and
`low_sample`.

**Observability** (Architecture §6, §12.4):
Step 6 is the only LLM-category step in Mode A that calls an OpenAI endpoint rather than
Anthropic. The Langfuse trace started by `PipelineExecutor` receives a child span for the
embedding call with `model`, `tokens_in`, `cost_usd`, and `latency_ms` attributes. This is
the integration point specified by REQ-N-008.

**Local-first / infinite TTL** (Architecture §2, Principle 2):
`event_embedding` rows have no TTL column and no expiry policy. Once persisted they are the
permanent historical archive. The `embed_event` step must check for an existing row before
calling the API; if a row exists it is returned directly (idempotent re-run safety).

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-001 | `embed_event` ≤ 2 s; `find_historical_analogies` ≤ 3 s (per-step stage-gate budgets in the Mode A 60 s processing window) | Both step functions accept a `timeout_seconds` parameter injected by `PipelineExecutor`; `asyncio.wait_for` enforces the timeout; `StepTimeoutError` is raised on breach |
| REQ-N-008 | Embedding API call logged as Langfuse span with token count and cost | `OpenAIEmbeddingService.embed()` accepts an optional `langfuse_span` context; records `tokens_in`, `cost_usd`, `model`, `latency_ms` on the span before returning |

## Component Design

### New Components
```
Module: ai (src/ai/embedding/)
  ├── EmbeddingService            — Protocol: embed(text: str) -> list[float]
  ├── OpenAIEmbeddingService      — Concrete adapter: calls text-embedding-3-small;
  │                                 accepts langfuse_span for observability;
  │                                 configured via OPENAI_API_KEY env var
  └── exceptions.py               — EmbeddingAPIError, EmbeddingTimeoutError

Module: storage (src/storage/repositories/)
  ├── EventEmbeddingRepository    — Protocol:
  │     save(event_id, embedding) -> None
  │     get_by_event_id(event_id) -> list[float] | None
  │     search_similar(embedding, k, min_outcome_count) -> list[AnalogSearchResult]
  └── EventEmbeddingRepositoryImpl — SQLAlchemy 2.0 async impl; pgvector cosine_distance
                                     operator for HNSW search; JOIN to event_exposure

Module: events (src/events/steps/)
  ├── embed_event.py              — Step 6: idempotency check → EmbeddingService call →
  │                                 EventEmbeddingRepository.save → Langfuse span
  └── find_historical_analogies.py — Step 7: EventEmbeddingRepository.search_similar →
                                      sample_size computation → low_sample flag

Module: events (src/events/models.py)  [extend existing]
  └── AnalogSearchResult          — Pydantic model per REQ-F-004 Data Models section
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/events/models.py` | Add `AnalogSearchResult`, `AnalogSearchResultSet` Pydantic models | Return type for step 7 consumed by step 8 |
| `src/events/steps/embed_event.py` | New file; wired into `PipelineExecutor` at step 6 slot | Step 6 implementation |
| `src/events/steps/find_historical_analogies.py` | New file; wired into `PipelineExecutor` at step 7 slot | Step 7 implementation |
| `src/storage/repositories/__init__.py` | Export `EventEmbeddingRepository` | Repository registration |
| `src/ai/__init__.py` | Export `EmbeddingService` protocol | Public surface for DI |

### Interfaces and Contracts

```python
# src/ai/embedding/service.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class EmbeddingService(Protocol):
    async def embed(
        self,
        text: str,
        span: Any | None = None,  # Langfuse span for observability
    ) -> list[float]:
        """Return VECTOR(1536) as a Python float list. Max 500 tokens accepted."""
        ...


# src/storage/repositories/event_embedding.py
from typing import Protocol
from uuid import UUID

class EventEmbeddingRepository(Protocol):
    async def save(self, event_id: UUID, embedding: list[float]) -> None:
        """Persist embedding; no-op if row already exists (idempotent)."""
        ...

    async def get_by_event_id(self, event_id: UUID) -> list[float] | None:
        """Return stored embedding or None if not yet embedded."""
        ...

    async def search_similar(
        self,
        embedding: list[float],
        k: int,
    ) -> list[AnalogSearchResult]:
        """
        HNSW cosine top-K search. Joins event_exposure for price_change_t1d.
        Computes sample_size (count of rows with non-null price_change_t1d).
        Sets low_sample=True on each result when sample_size < 5.
        """
        ...


# src/events/models.py  (additions)
class AnalogSearchResult(BaseModel):
    event_id: UUID
    similarity_score: float
    event_title: str
    event_date: datetime
    intensity: int
    category: list[str]
    price_change_t1d: float | None
    sample_size: int
    low_sample: bool

class AnalogSearchResultSet(BaseModel):
    results: list[AnalogSearchResult]
    k_requested: int
    low_sample: bool          # True if any result has low_sample=True
    source_event_id: UUID
```

## Implementation Tasks

### TASK-001: EmbeddingService protocol and OpenAI adapter · M/TDD · src/ai/embedding/service.py, src/ai/embedding/openai_embedding_service.py, src/ai/embedding/exceptions.py, tests/unit/ai/test_openai_embedding_service.py

Implement the `EmbeddingService` protocol and the `OpenAIEmbeddingService` concrete adapter.
The adapter calls `openai.AsyncOpenAI.embeddings.create(model="text-embedding-3-small",
input=text)`, truncating input to 500 tokens before the call (tiktoken cl100k_base encoder).
It records a Langfuse child span when `span` is provided, attaching `tokens_in`,
`cost_usd` (computed as `tokens_in * 0.00000002`, the current published rate), `model`, and
`latency_ms`. On HTTP error or timeout it raises `EmbeddingAPIError`. The service is
configured exclusively from `OPENAI_API_KEY` env var loaded via `src/config/settings.py`;
it never hard-codes credentials.

**Tests to write first (TDD):**
- `test_embed_returns_vector_1536_length` — mock OpenAI client returns 1536 floats; assert
  service returns list of length 1536.
- `test_embed_truncates_to_500_tokens` — input exceeding 500 tokens is truncated before the
  API call; assert the mocked client receives text of ≤ 500 tokens.
- `test_embed_records_langfuse_span_attributes` — when span mock is provided, assert
  `tokens_in`, `cost_usd`, `model`, and `latency_ms` are set on the span.
- `test_embed_raises_embedding_api_error_on_http_failure` — mock raises `openai.APIError`;
  assert `EmbeddingAPIError` is raised with original error wrapped.

**AC covered:** AC-001 (embedding API call), AC-005 (Langfuse span via REQ-N-008)

---

### TASK-002: EventEmbeddingRepository interface and SQLAlchemy implementation · M/TDD · src/storage/repositories/event_embedding.py, src/storage/repositories/event_embedding_impl.py, tests/unit/storage/test_event_embedding_repository.py

Implement `EventEmbeddingRepository` protocol and `EventEmbeddingRepositoryImpl` using
SQLAlchemy 2.0 async. `save()` executes an `INSERT ... ON CONFLICT (event_id) DO NOTHING`
to guarantee idempotency. `get_by_event_id()` is a simple primary key lookup. `search_similar()`
issues:

```sql
SELECT
    ge.event_id, ge.title AS event_title, ge.occurred_at AS event_date,
    ge.intensity, ge.category,
    (1 - (ee.embedding <=> :query_vec)) AS similarity_score,
    ee2.price_change_t1d,
    COUNT(ee2.price_change_t1d) OVER (PARTITION BY TRUE) AS sample_size
FROM event_embedding ee
JOIN geo_event ge ON ge.event_id = ee.event_id
LEFT JOIN event_exposure ee2 ON ee2.event_id = ee.event_id
WHERE ee.event_id != :source_event_id
ORDER BY ee.embedding <=> :query_vec
LIMIT :k
```

`sample_size` is the count of returned rows where `price_change_t1d IS NOT NULL`.
`low_sample` is set `True` on the result set when `sample_size < 5`. All query parameters
are bound, never interpolated (Security baseline). Export the protocol from
`src/storage/repositories/__init__.py`.

**Tests to write first (TDD):**
- `test_save_persists_embedding_row` — against test DB; assert row exists after save.
- `test_save_is_idempotent` — call save twice with same event_id; assert no unique-violation
  and only one row exists.
- `test_get_by_event_id_returns_none_for_missing` — event_id not in table returns None.
- `test_search_similar_returns_top_k_ordered_by_score` — seed 10 rows; assert top-K results
  are sorted descending by similarity_score.
- `test_search_similar_sets_low_sample_true_when_fewer_than_5_outcomes` — seed results with
  3 non-null `price_change_t1d`; assert `low_sample=True` and `sample_size=3`.

**AC covered:** AC-002 (top-K search), AC-003 (low_sample flag and sample_size), AC-005 (persistence)

---

### TASK-003: `embed_event` step function (Mode A step 6) · M/TDD · src/events/steps/embed_event.py, tests/unit/events/steps/test_embed_event.py

Implement `embed_event(ctx: PipelineContext) -> PipelineContext`. The function:

1. Checks `EventEmbeddingRepository.get_by_event_id(ctx.event_id)` — if embedding exists,
   populates `ctx.embedding` and returns immediately (idempotent, no API call, no cost).
2. Otherwise calls `EmbeddingService.embed(ctx.event_text, span=ctx.langfuse_span)`.
3. Calls `EventEmbeddingRepository.save(ctx.event_id, embedding)`.
4. Populates `ctx.embedding` and returns the updated context.

The function is wrapped with `asyncio.wait_for` using `timeout_seconds=2.0` (injected from
`PipelineExecutor`); raises `StepTimeoutError` on breach. Both `EmbeddingService` and
`EventEmbeddingRepository` are injected; no `new ConcreteClass()` inside the function
(Dependency Inversion).

**Tests to write first (TDD):**
- `test_embed_event_calls_api_and_persists_when_not_cached` — mock repository returns None;
  assert service.embed called once; assert repository.save called with correct args.
- `test_embed_event_skips_api_when_already_persisted` — mock repository returns existing
  embedding; assert service.embed NOT called.
- `test_embed_event_populates_ctx_embedding` — assert ctx.embedding is set to returned vector.
- `test_embed_event_raises_step_timeout_error` — mock service.embed sleeps 3 s; assert
  `StepTimeoutError` raised.

**AC covered:** AC-001 (embed and persist within 2 s), AC-005 (immutable / no re-fetch)

---

### TASK-004: `find_historical_analogies` step function (Mode A step 7) · M/TDD · src/events/steps/find_historical_analogies.py, tests/unit/events/steps/test_find_historical_analogies.py

Implement `find_historical_analogies(ctx: PipelineContext) -> PipelineContext`. The
function:

1. Reads `ctx.embedding` (populated by step 6); raises `PipelineError` if None.
2. Calls `EventEmbeddingRepository.search_similar(ctx.embedding, k=ctx.settings.analogy_k)`
   where `analogy_k` defaults to 5 and is configurable via `Settings`.
3. Builds `AnalogSearchResultSet` with `low_sample` derived from the result set.
4. Populates `ctx.analogy_result_set` and returns.

The function is wrapped with `asyncio.wait_for` using `timeout_seconds=3.0` (injected from
`PipelineExecutor`); raises `StepTimeoutError` on breach. `analogy_k` is not hardcoded —
it is read from `Settings.analogy_k` (default 5, overridable via env var `ANALOGY_K`).

**Tests to write first (TDD):**
- `test_find_analogies_returns_result_set_with_k_results` — mock repository returns K items;
  assert result set has K entries.
- `test_find_analogies_sets_low_sample_true_when_fewer_than_5_outcomes` — mock result has
  sample_size=3; assert `ctx.analogy_result_set.low_sample` is True.
- `test_find_analogies_raises_pipeline_error_if_no_embedding` — ctx.embedding is None;
  assert `PipelineError` raised.
- `test_find_analogies_raises_step_timeout_error` — mock repo sleeps 4 s; assert
  `StepTimeoutError` raised.
- `test_find_analogies_uses_configurable_k` — set `analogy_k=10`; assert repository called
  with `k=10`.

**AC covered:** AC-002 (top-K HNSW search, configurable K), AC-003 (low_sample flag), AC-004 (within stage-gate budget)

---

### TASK-005: `AnalogSearchResult` and `AnalogSearchResultSet` Pydantic models · S/no-TDD · src/events/models.py

Extend `src/events/models.py` with `AnalogSearchResult` and `AnalogSearchResultSet` per the
interfaces section. All fields must have explicit types and no `Any`. `low_sample` on
`AnalogSearchResultSet` is the authoritative aggregate flag; it is `True` when
`sample_size < 5`. Add `analogy_result_set: AnalogSearchResultSet | None = None` to
`PipelineContext`.

**AC covered:** enables AC-002, AC-003 (model shape)

---

### TASK-006: Settings entry for `analogy_k` and HNSW index migration · S/no-TDD · src/config/settings.py, migrations/versions/xxxx_add_event_embedding_hnsw_index.py

Add `analogy_k: int = Field(default=5, ge=1, le=50, env="ANALOGY_K")` to
`src/config/settings.py`. Create an Alembic migration that:

1. Creates the `event_embedding` table if not already created by PLAN-F-031's migration
   (use `IF NOT EXISTS` guard).
2. Adds the HNSW index: `CREATE INDEX IF NOT EXISTS idx_event_embedding_hnsw ON
   event_embedding USING hnsw (embedding vector_cosine_ops)`.

The migration is non-destructive and idempotent. Add a module-level comment that the HNSW
index only becomes useful after PLAN-F-031 cold-start seeding completes.

**AC covered:** AC-004 (HNSW index in place for search performance)

---

### TASK-007: Integration smoke test for embed + search round-trip · M/TDD · tests/integration/events/test_embed_analogy_pipeline.py

Write an integration test against a real PostgreSQL test instance with pgvector. The test:

1. Seeds 10 `geo_event` + `event_embedding` rows with synthetic VECTOR(1536) data and mixed
   `price_change_t1d` values (some null, some non-null).
2. Calls `embed_event` with a mocked `EmbeddingService` that returns a deterministic vector.
3. Calls `find_historical_analogies` directly against the test DB.
4. Asserts: result count ≤ 10, results are sorted by similarity descending, `low_sample`
   flag is correct based on seeded outcome counts.
5. Calls `embed_event` a second time with the same event_id and asserts the mocked service
   is NOT called again (idempotency).

This test does NOT call the real OpenAI API; it uses a mock embedding service.

**Tests to write first (TDD):**
- `test_round_trip_embed_and_search_returns_sorted_results`
- `test_round_trip_low_sample_flag_correct_for_sparse_outcomes`
- `test_embed_event_is_idempotent_on_second_call`

**AC covered:** AC-001 (persistence), AC-002 (sorted results), AC-003 (low_sample), AC-005 (idempotency)

## Acceptance Criteria Coverage

- AC-001: embed_event calls OpenAI text-embedding-3-small, stores VECTOR(1536), completes ≤ 2 s → TASK-001, TASK-003, TASK-007
- AC-002: search returns top-K historical event IDs sorted by similarity, K configurable (default ≥ 5) → TASK-002, TASK-004, TASK-005, TASK-006, TASK-007
- AC-003: fewer than 5 valid price_change_t1d outcomes sets low_sample=true and records accurate sample_size → TASK-002, TASK-004, TASK-005, TASK-007
- AC-004: with HNSW index populated, similarity search completes within stage-gate budget → TASK-004, TASK-006
- AC-005: newly stored embedding is retrievable as a historical analogy without re-fetching from API (infinite TTL, idempotent save) → TASK-001, TASK-002, TASK-003, TASK-007

## Risks and Notes

- **HNSW index dependency:** Until PLAN-F-031 cold-start seeding completes, `find_historical_analogies` will return 0–few results. This is expected and not a defect. The `low_sample` flag will be `True` for all results during this period, which correctly triggers disclaimers in any downstream recommendation step.
- **pgvector operator availability:** The `<=>` cosine distance operator requires pgvector 0.5+. The migration in TASK-006 will fail fast on an environment lacking the extension, surfacing the dependency clearly.
- **Token truncation:** OpenAI text-embedding-3-small accepts up to 8191 tokens, but the architecture specifies 500 tokens for step 6. TASK-001 enforces this truncation to control cost and latency predictably. Use tiktoken cl100k_base for accurate token counting.
- **OpenAI key separation:** The project uses Anthropic exclusively for LLM tasks (D6), but OpenAI is required for embeddings. `OPENAI_API_KEY` must be present in `.env.example` with a comment explaining its exclusive embedding use.
- **Cost per embedding:** At the published text-embedding-3-small rate ($0.00000002/token), 500 tokens costs $0.00001 per event — well within the $0.05 per-event ceiling from REQ-N-003. The Langfuse span records the exact cost for audit purposes.
- **PLAN-F-001 coupling:** This plan delivers the implementations of steps 6 and 7 as Python modules. They are wired into `PipelineExecutor` from PLAN-F-001 via constructor injection. If PLAN-F-001 is not yet implemented, the step files can still be unit-tested in isolation; the wiring is a one-line change in the executor.
