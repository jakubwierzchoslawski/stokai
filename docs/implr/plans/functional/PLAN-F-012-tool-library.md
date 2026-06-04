---
plan_id: PLAN-F-012
slug: tool-library
title: Agent Tool Library
linked_requirement: REQ-F-012
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-006, reason: "tenant_id included in every DB lookup — structurally enforced via base tool contract" }
  - { id: REQ-N-011, reason: "all data reads flow through the cache-or-fetch layer from PLAN-F-032" }
dependencies:
  - { id: PLAN-F-032, reason: "Tool library relies on cache-or-fetch pattern for data retrieval" }
  - { id: PLAN-F-011, reason: "Tool library wraps AgentDefinition.tools allowlist; ToolGuard from PLAN-F-011 enforces per-agent access" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-012 — Agent Tool Library

## Linked Requirement
**REQ-F-012** — Agent Tool Library
Status: approved | Jira:

## Objective
Build the complete Tool Library that forms the hard boundary between all Mode B agents and every data source. This plan introduces: (1) Pydantic `ToolResult`, `ToolError`, and `ToolCacheEntry` contracts with a 50-row bounded output guarantee; (2) a `BaseTool` abstract class that encodes the standard error contract (`ToolNotApplicable` | `InsufficientData` | `RateLimited`), per-workflow-run result caching keyed on `(run_id, tool_name, args_hash)`, and tenant-isolation enforcement; (3) six concrete tool families — Portfolio Context (3 tools), Company Data (3 tools), Events + History (3 tools), Exposure + Correlation (2 tools), Macro + Market (2 tools), Memory + Track Record (3 tools); (4) a `ToolRegistry` that loads tools by name so agents resolve them from their YAML `tools` list at runtime; and (5) a `ToolCallLogger` that writes every call to the `tool_call` agentic table and decorates each call as a Langfuse child span. After this plan, no agent in any workflow reads from the database or calls an external API directly — all data access flows through named tool calls.

## Architecture Context
This plan lives entirely in the `ai` backend module (`src/ai/`, Architecture §5 and §7.3). It extends the `src/ai/` package introduced by PLAN-F-011 with a new `tools/` sub-package. The Tool Library sits at the boundary between Layer 4 — Processing (agents, workflows) and Layer 3 — Storage plus Layer 2 — Ingestion & Cache (Architecture §4). Every tool call delegates data retrieval to the `cache_or_fetch` decorator from `src/ingestion/` (PLAN-F-032), satisfying the Local-First Data principle (Architecture §2 Principle 2) and REQ-N-011. The `tenant_id` parameter is threaded through every tool input model and injected into every repository query, satisfying REQ-N-006 and Architecture §12.3. The per-workflow-run result cache is a lightweight in-memory dict keyed on `(run_id, tool_name, args_hash)` passed inside the `WorkflowState` (Architecture §7.1), preventing duplicate DB reads within a single workflow execution. The `ToolCallLogger` writes `tool_call` rows (Architecture §10 agentic tables) and opens Langfuse child spans for observability (Architecture §12.4). The `ToolRegistry` maps string names from agent YAML `tools:` lists (PLAN-F-011) to callable `BaseTool` instances, fulfilling Architecture §7.3's requirement that tools are accessible by name from the agent execution context.

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-006 | `tenant_id` in every DB lookup — structural enforcement | `BaseToolInput` carries a required `tenant_id: UUID` field; `BaseTool.execute` passes it to every repository call; no tool may skip the field (validated by Pydantic on every invocation) |
| REQ-N-011 | All data reads go through cache-or-fetch layer | Every concrete tool's `_fetch` method calls `CacheOrFetch.cache_or_fetch(...)` from PLAN-F-032; no tool is permitted to call a repository or provider adapter directly without the cache-or-fetch wrapper |

## Component Design

### New Components
```
Package: src/ai/tools/
  ├── __init__.py                     — public surface: ToolRegistry, BaseTool, ToolResult, ToolError
  ├── base.py                         — BaseTool ABC; ToolResult, ToolError, ToolCacheEntry models;
  │                                     BaseToolInput; ToolErrorType enum; 50-row bound; run-cache
  ├── registry.py                     — ToolRegistry (IToolRegistry protocol + implementation)
  ├── logging.py                      — ToolCallLogger (tool_call DB row + Langfuse child span)
  ├── exceptions.py                   — ToolNotApplicable, InsufficientData, RateLimited error classes
  └── families/
      ├── __init__.py
      ├── portfolio_context.py        — GetPortfolioPositions, GetWatchlist, GetScoringProfile
      ├── company_data.py             — GetCompanyFundamentals, GetCompanyScores, GetPriceHistory
      ├── events_history.py           — GetEventsByCompany, GetEventAnalogies, GetAiRecommendationHistory
      ├── exposure_correlation.py     — GetEventExposure, GetCompanyExposureHistory
      ├── macro_market.py             — GetMacroIndicators, GetSectorPerformance
      └── memory_track_record.py     — GetSemanticFacts, GetProceduralPatterns, GetRecommendationOutcomes

Tests:
tests/unit/ai/tools/
  ├── test_base_tool.py               — ToolResult bounds, caching, error contract
  ├── test_tool_registry.py           — registry resolution, name→tool mapping
  ├── test_tool_call_logger.py        — DB write and Langfuse span
  ├── test_portfolio_context_tools.py
  ├── test_company_data_tools.py
  ├── test_events_history_tools.py
  ├── test_exposure_correlation_tools.py
  ├── test_macro_market_tools.py
  └── test_memory_track_record_tools.py
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/ai/__init__.py` | Export `ToolRegistry`, `BaseTool`, `ToolResult`, `ToolError` | Downstream workflows import from `src/ai` |
| `src/ai/startup.py` | Register all tool instances into `ToolRegistry` during `initialise_ai_module` | Tools must be resolvable by name before any workflow runs |

### Interfaces and Contracts

```python
# src/ai/tools/base.py

from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable
from enum import StrEnum
from typing import Any
from uuid import UUID
import hashlib, json
from pydantic import BaseModel, Field

MAX_ROWS = 50  # hard architectural limit; never exceed

class ToolErrorType(StrEnum):
    TOOL_NOT_APPLICABLE = "ToolNotApplicable"
    INSUFFICIENT_DATA   = "InsufficientData"
    RATE_LIMITED        = "RateLimited"

class ToolError(BaseModel):
    error_type: ToolErrorType
    message: str
    retry_after: int | None = None  # seconds; only for RateLimited

class ToolResult(BaseModel):
    data: list[dict[str, Any]] = Field(max_length=MAX_ROWS)
    truncated: bool = False
    row_count: int

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> "ToolResult":
        truncated = len(rows) > MAX_ROWS
        bounded = rows[:MAX_ROWS]
        return cls(data=bounded, truncated=truncated, row_count=len(bounded))

class ToolCacheEntry(BaseModel):
    run_id: UUID
    tool_name: str
    args_hash: str
    result: ToolResult

class BaseToolInput(BaseModel):
    tenant_id: UUID          # required on every tool call — REQ-N-006

class BaseTool(ABC):
    """
    Abstract base for every tool in the library.
    Subclasses implement _execute; BaseTool handles:
      - per-workflow-run result cache
      - 50-row bound (enforced by ToolResult.from_rows)
      - standard ToolError contract (ToolNotApplicable, InsufficientData, RateLimited)
      - ToolCallLogger delegation
    """
    name: str  # must match the identifier in agent YAML tools list

    def __init__(self, cache_or_fetch: CacheOrFetch, logger: ToolCallLogger) -> None:
        self._cof = cache_or_fetch
        self._logger = logger
        self._run_cache: dict[str, ToolResult] = {}  # keyed by args_hash within run

    def _args_hash(self, inputs: BaseToolInput) -> str:
        payload = inputs.model_dump_json(exclude={"tenant_id"})
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    async def execute(
        self,
        inputs: BaseToolInput,
        run_id: UUID,
        run_cache: dict[str, ToolResult],
    ) -> ToolResult | ToolError:
        """
        1. Compute args_hash.
        2. Check run_cache[(run_id, self.name, args_hash)].
        3. Cache hit → return cached ToolResult.
        4. Cache miss → call _execute → store in run_cache → return.
        5. Map exceptions to ToolError contract.
        """
        ...

    @abstractmethod
    async def _execute(self, inputs: BaseToolInput) -> list[dict[str, Any]]:
        """
        Fetch data via self._cof (cache-or-fetch).
        Must pass inputs.tenant_id to every repository call.
        Returns raw rows; BaseTool.execute bounds and wraps them.
        """
        ...
```

```python
# src/ai/tools/exceptions.py

class ToolNotApplicable(Exception):
    """Tool cannot apply to the given query context."""
    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"ToolNotApplicable({tool_name}): {reason}")

class InsufficientData(Exception):
    """Not enough data available to produce a meaningful result."""
    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"InsufficientData({tool_name}): {reason}")

class RateLimited(Exception):
    """External source is rate-limited; retry after `retry_after` seconds."""
    def __init__(self, tool_name: str, source: str, retry_after: int | None = None) -> None:
        self.tool_name = tool_name
        self.source = source
        self.retry_after = retry_after
        super().__init__(f"RateLimited({tool_name}) from {source}")
```

```python
# src/ai/tools/registry.py

from typing import Protocol
from src.ai.tools.base import BaseTool

class IToolRegistry(Protocol):
    def resolve(self, tool_name: str) -> BaseTool:
        """Return the BaseTool for tool_name. Raises ToolNotFoundError if missing."""
        ...
    def all_tools(self) -> list[BaseTool]: ...

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def resolve(self, tool_name: str) -> BaseTool:
        if tool_name not in self._tools:
            raise ToolNotFoundError(tool_name, sorted(self._tools))
        return self._tools[tool_name]

    def all_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

class ToolNotFoundError(KeyError):
    def __init__(self, tool_name: str, available: list[str]) -> None:
        self.tool_name = tool_name
        self.available = available
        super().__init__(f"Tool {tool_name!r} not in registry. Available: {available}")
```

```python
# src/ai/tools/logging.py

from uuid import UUID
from src.ai.tools.base import ToolResult, ToolError

class ToolCallLogger:
    """
    Writes a tool_call row (Architecture §10 agentic tables) and
    opens a Langfuse child span for every tool invocation.
    Injected into BaseTool; never instantiated inside a tool.
    If Langfuse client is None, DB write still occurs (observability degrades gracefully).
    """
    async def log(
        self,
        invocation_id: UUID,
        tool_name: str,
        arguments: dict,
        result: ToolResult | ToolError,
        duration_ms: int,
        cached: bool,
    ) -> None: ...
```

Tool input/output models (representative — executor must implement all 16):

```python
# src/ai/tools/families/portfolio_context.py (representative)

from uuid import UUID
from pydantic import BaseModel
from src.ai.tools.base import BaseToolInput

class GetPortfolioPositionsInput(BaseToolInput):
    user_id: UUID

class PortfolioPosition(BaseModel):
    company_id: UUID
    ticker: str
    shares: float
    cost_basis: float

# tool name: "get_portfolio_positions"
# → returns list[PortfolioPosition] bounded to MAX_ROWS


# src/ai/tools/families/company_data.py (representative)
from datetime import date
from pydantic import BaseModel
from src.ai.tools.base import BaseToolInput

class GetPriceHistoryInput(BaseToolInput):
    ticker: str
    from_date: date
    to_date: date
    interval: str   # "1d" | "1h" | "15m"

# tool name: "get_price_history"
# → returns list[OHLCVBar] bounded to MAX_ROWS
```

---

## Implementation Tasks

### TASK-001: ToolResult, ToolError, ToolCacheEntry models and ToolErrorType enum · M/TDD · src/ai/tools/base.py,src/ai/tools/exceptions.py,src/ai/tools/__init__.py,tests/unit/ai/tools/test_base_tool.py

Define the three Pydantic data models (`ToolResult`, `ToolError`, `ToolCacheEntry`) and the `ToolErrorType` enum. `ToolResult.from_rows(rows)` must truncate any list exceeding 50 items and set `truncated=True`. The `data` field uses `max_length=MAX_ROWS` as a secondary declarative guard. `ToolError` must be JSON-serializable with no custom `__str__` trickery — it is stored verbatim in `workflow_run.final_state`. `ToolCacheEntry` includes the `run_id + tool_name + args_hash` composite key. Define the three exception classes in `exceptions.py` (`ToolNotApplicable`, `InsufficientData`, `RateLimited`) with structured attributes so `BaseTool.execute` can map them to `ToolError` instances unambiguously.

**Tests to write first (TDD):**
- `test_tool_result_from_rows_under_50_sets_truncated_false`
- `test_tool_result_from_rows_exactly_50_sets_truncated_false`
- `test_tool_result_from_rows_over_50_truncates_to_50_sets_truncated_true`
- `test_tool_result_row_count_matches_bounded_data_length`
- `test_tool_error_is_json_serializable` — `json.dumps(err.model_dump())` must not raise
- `test_tool_not_applicable_carries_tool_name_and_reason`
- `test_rate_limited_carries_retry_after_seconds`
- `test_insufficient_data_message_propagated`

**AC covered**: AC-001, AC-003

---

### TASK-002: BaseTool ABC — run-cache, bounds, and error-contract execution wrapper · M/TDD · src/ai/tools/base.py,tests/unit/ai/tools/test_base_tool.py

Implement `BaseTool.execute` with the full five-step logic: (1) compute `args_hash` from inputs excluding `tenant_id`; (2) construct the run-cache key as `f"{run_id}:{self.name}:{args_hash}"`; (3) return cached `ToolResult` on hit; (4) on miss call `_execute`, wrap rows with `ToolResult.from_rows`, store in `run_cache`; (5) map `ToolNotApplicable` → `ToolError(TOOL_NOT_APPLICABLE)`, `InsufficientData` → `ToolError(INSUFFICIENT_DATA)`, `RateLimited` → `ToolError(RATE_LIMITED, retry_after=...)`. Uncaught exceptions must propagate — do not swallow unknown errors as `ToolError`. The `args_hash` excludes `tenant_id` so the same logical query by two tenants does not collide in the run-level cache (each workflow run is single-tenant). Delegate timing and DB write to `ToolCallLogger.log` after every execution (cached or not). Define `BaseToolInput` with required `tenant_id: UUID`.

**Tests to write first (TDD):**
- `test_second_call_with_same_args_returns_cached_result_without_calling_execute`
- `test_second_call_with_different_run_id_calls_execute_again` — different run_id means new cache scope
- `test_tool_not_applicable_exception_maps_to_tool_error_of_correct_type`
- `test_insufficient_data_exception_maps_to_tool_error`
- `test_rate_limited_exception_maps_to_tool_error_with_retry_after`
- `test_unknown_exception_propagates_uncaught`
- `test_base_tool_input_requires_tenant_id` — missing tenant_id raises Pydantic ValidationError
- `test_args_hash_excludes_tenant_id` — two inputs differing only in tenant_id produce the same hash
- `test_logger_called_on_cache_hit_with_cached_true`
- `test_logger_called_on_cache_miss_with_cached_false`

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

### TASK-003: ToolRegistry and ToolCallLogger · M/TDD · src/ai/tools/registry.py,src/ai/tools/logging.py,tests/unit/ai/tools/test_tool_registry.py,tests/unit/ai/tools/test_tool_call_logger.py

Implement `ToolRegistry` with `register(tool)`, `resolve(tool_name)`, and `all_tools()`. `resolve` raises `ToolNotFoundError` (a `KeyError` subclass) when the name is not registered. Register names are case-sensitive and must match exactly the identifier in the agent YAML `tools:` list (snake_case, e.g. `"get_portfolio_positions"`). Implement `ToolCallLogger` with an injected SQLAlchemy `AsyncSession` and optional Langfuse client. `log(...)` writes one `tool_call` row (Architecture §10: `tool_call_id`, `invocation_id`, `tool_name`, `arguments JSONB`, `result JSONB`, `duration_ms`, `cost_tier`, `cached BOOL`) and opens/closes a Langfuse child span if the client is available. If the Langfuse client is `None`, the method completes with only the DB write — no exception. If the DB write fails, the error is logged at `ERROR` level and swallowed (logging must never break tool execution).

**Tests to write first (TDD):**
- `test_registry_resolve_returns_registered_tool`
- `test_registry_resolve_unknown_name_raises_tool_not_found_error`
- `test_registry_all_tools_returns_all_registered`
- `test_registry_is_case_sensitive` — `"Get_Portfolio_Positions"` not the same as `"get_portfolio_positions"`
- `test_logger_writes_tool_call_row` — mock AsyncSession; assert `session.add` called with correct fields
- `test_logger_sets_cached_true_on_cache_hit`
- `test_logger_no_ops_on_langfuse_when_client_is_none`
- `test_logger_swallows_db_write_failure_and_logs_error`

**AC covered**: AC-002, AC-004, AC-005

---

### TASK-004: Portfolio Context tool family · M/TDD · src/ai/tools/families/portfolio_context.py,tests/unit/ai/tools/test_portfolio_context_tools.py

Implement three tools: `GetPortfolioPositions`, `GetWatchlist`, and `GetScoringProfile`. Each has a typed `Input` model extending `BaseToolInput`. Every `_execute` method calls `cache_or_fetch` with the appropriate `DataType` and a repository fetch function that includes `tenant_id` in the WHERE clause. `GetPortfolioPositions(user_id)` queries `position JOIN portfolio` filtered by `portfolio.tenant_id = tenant_id AND portfolio.user_id = user_id`. `GetWatchlist(user_id)` queries `watchlist` filtered by `tenant_id`. `GetScoringProfile(user_id)` retrieves the user's active `indicator` profile filtered by `tenant_id`. Tool names must match exactly: `"get_portfolio_positions"`, `"get_watchlist"`, `"get_scoring_profile"`.

**Tests to write first (TDD):**
- `test_get_portfolio_positions_returns_bounded_result`
- `test_get_portfolio_positions_includes_tenant_id_in_query`
- `test_get_portfolio_positions_raises_insufficient_data_when_no_positions`
- `test_get_watchlist_returns_watchlist_companies`
- `test_get_watchlist_includes_tenant_id_in_query`
- `test_get_scoring_profile_returns_active_profile`
- `test_get_scoring_profile_raises_tool_not_applicable_for_unknown_user`

**AC covered**: AC-001, AC-003, AC-004, AC-005

---

### TASK-005: Company Data tool family · M/TDD · src/ai/tools/families/company_data.py,tests/unit/ai/tools/test_company_data_tools.py

Implement three tools: `GetCompanyFundamentals`, `GetCompanyScores`, and `GetPriceHistory`. `GetCompanyFundamentals(ticker, tenant_id)` fetches fundamentals via `cache_or_fetch(DataType.FUNDAMENTALS, ...)`. `GetCompanyScores(company_id, profile_id, tenant_id)` queries `company_score` filtered by `tenant_id`; returns current scores with breakdown. `GetPriceHistory(ticker, from_date, to_date, interval, tenant_id)` queries the `price_bar` TimescaleDB hypertable; date range capped to return at most 50 rows (callers must request a date range appropriate to the interval). All three delegate fetching to `CacheOrFetch`. Tool names: `"get_company_fundamentals"`, `"get_company_scores"`, `"get_price_history"`.

**Tests to write first (TDD):**
- `test_get_company_fundamentals_returns_fundamentals_data`
- `test_get_company_fundamentals_uses_cache_or_fetch`
- `test_get_company_scores_filters_by_tenant_id`
- `test_get_company_scores_raises_insufficient_data_when_no_scores`
- `test_get_price_history_returns_at_most_50_bars`
- `test_get_price_history_truncated_flag_set_when_range_exceeds_50`
- `test_get_price_history_raises_tool_not_applicable_for_unknown_ticker`

**AC covered**: AC-001, AC-003, AC-004, AC-005

---

### TASK-006: Events + History tool family · M/TDD · src/ai/tools/families/events_history.py,tests/unit/ai/tools/test_events_history_tools.py

Implement three tools: `GetEventsByCompany`, `GetEventAnalogies`, and `GetAiRecommendationHistory`. `GetEventsByCompany(company_id, from_date, to_date, tenant_id)` queries `event_exposure JOIN geo_event` for the company's events within the date range, respecting `geo_event.tenant_id IS NULL OR geo_event.tenant_id = tenant_id` (global events visible to all tenants). `GetEventAnalogies(event_id, top_k, tenant_id)` calls the pgvector HNSW cosine search on `event_embedding` via the `historical` module interface; `top_k` is capped at `MAX_ROWS`. `GetAiRecommendationHistory(company_id, tenant_id)` queries `ai_recommendation` filtered by `company_id` and `tenant_id`. Tool names: `"get_events_by_company"`, `"get_event_analogies"`, `"get_ai_recommendation_history"`.

**Tests to write first (TDD):**
- `test_get_events_by_company_includes_global_events`
- `test_get_events_by_company_includes_tenant_scoped_events`
- `test_get_events_by_company_excludes_other_tenant_events`
- `test_get_event_analogies_caps_top_k_at_50`
- `test_get_event_analogies_raises_insufficient_data_when_no_embeddings`
- `test_get_ai_recommendation_history_filters_by_tenant_id`
- `test_get_ai_recommendation_history_returns_bounded_result`

**AC covered**: AC-001, AC-003, AC-004, AC-005

---

### TASK-007: Exposure + Correlation tool family · S/no-TDD · src/ai/tools/families/exposure_correlation.py

Implement two tools: `GetEventExposure` and `GetCompanyExposureHistory`. `GetEventExposure(event_id, tenant_id)` queries `event_exposure` for all rows associated with the event; the `geo_event.tenant_id` visibility rule from TASK-006 applies. `GetCompanyExposureHistory(company_id, tenant_id)` queries the history of `event_exposure` rows for the company filtered by `tenant_id`. Both tools return at most 50 rows via `ToolResult.from_rows`. Tool names: `"get_event_exposure"`, `"get_company_exposure_history"`.

**AC covered**: AC-001, AC-003, AC-005

---

### TASK-008: Macro + Market tool family · M/TDD · src/ai/tools/families/macro_market.py,tests/unit/ai/tools/test_macro_market_tools.py

Implement two tools: `GetMacroIndicators` and `GetSectorPerformance`. `GetMacroIndicators(indicator_list, tenant_id)` fetches FRED/World Bank series from `cache_or_fetch(DataType.MACRO, ...)` for each indicator in `indicator_list`; if `len(indicator_list) > MAX_ROWS` the list is truncated and `truncated=True` in the result. `GetSectorPerformance(sector, from_date, to_date, tenant_id)` queries aggregated price bar metrics per sector from the `price_bar` hypertable; rows bounded to 50. For `RateLimited` from the FRED adapter, this tool must surface `ToolError(RATE_LIMITED, retry_after=...)` to the agent rather than raising. Tool names: `"get_macro_indicators"`, `"get_sector_performance"`.

**Tests to write first (TDD):**
- `test_get_macro_indicators_returns_requested_series`
- `test_get_macro_indicators_truncates_indicator_list_above_50`
- `test_get_macro_indicators_maps_rate_limited_to_tool_error`
- `test_get_sector_performance_returns_bounded_rows`
- `test_get_sector_performance_filters_by_sector`

**AC covered**: AC-001, AC-003, AC-005

---

### TASK-009: Memory + Track Record tool family · M/TDD · src/ai/tools/families/memory_track_record.py,tests/unit/ai/tools/test_memory_track_record_tools.py

Implement three tools: `GetSemanticFacts`, `GetProceduralPatterns`, and `GetRecommendationOutcomes`. `GetSemanticFacts(entity_id, tenant_id)` queries `semantic_fact` for facts related to the entity; uses pgvector cosine similarity on `semantic_fact.embedding` if an embedding for `entity_id` is available, otherwise falls back to an exact-match on `namespace`. Returns at most 50 facts. `GetProceduralPatterns(context_tags, tenant_id)` queries `procedural_pattern` filtered by matching `context_tags` against `recommended_for_agents`; returns patterns ordered by `success_rate DESC` limited to 50. `GetRecommendationOutcomes(company_id, tenant_id)` queries `recommendation_outcome JOIN ai_recommendation` for the company's historical recommendation accuracy. Tool names: `"get_semantic_facts"`, `"get_procedural_patterns"`, `"get_recommendation_outcomes"`.

**Tests to write first (TDD):**
- `test_get_semantic_facts_returns_bounded_result`
- `test_get_semantic_facts_filters_by_entity_id`
- `test_get_procedural_patterns_returns_ordered_by_success_rate`
- `test_get_procedural_patterns_raises_insufficient_data_when_no_patterns_match`
- `test_get_recommendation_outcomes_filters_by_tenant_id_and_company_id`
- `test_get_recommendation_outcomes_returns_bounded_result`

**AC covered**: AC-001, AC-003, AC-005

---

### TASK-010: ToolRegistry wired into startup; all 16 tools registered · S/no-TDD · src/ai/startup.py,src/ai/tools/__init__.py

Extend `initialise_ai_module` from PLAN-F-011 to (1) construct a `ToolRegistry`; (2) instantiate all 16 tool classes, injecting their `CacheOrFetch` and `ToolCallLogger` dependencies; (3) call `registry.register(tool)` for each; (4) store the registry on `app.state.tool_registry`; (5) verify that every `tool_name` declared in every loaded `AgentDefinition.tools` list resolves in the registry — raise `StartupValidationError` for any name that does not. This step prevents agent YAMLs from referencing tool names that do not exist, catching mismatches at startup rather than at runtime during a live workflow.

**AC covered**: AC-005

---

### TASK-011: Cross-tool unit tests — cache-hit, bounds enforcement, error contract, tenant isolation · M/TDD · tests/unit/ai/tools/test_base_tool.py,tests/unit/ai/tools/test_portfolio_context_tools.py,tests/unit/ai/tools/test_company_data_tools.py,tests/unit/ai/tools/test_events_history_tools.py,tests/unit/ai/tools/test_macro_market_tools.py,tests/unit/ai/tools/test_memory_track_record_tools.py

Produce a dedicated cross-cutting test suite covering: (1) cache-hit invariant — given any tool called twice with identical `(run_id, tool_name, args)`, the second call does not trigger `_execute`; (2) bounds enforcement — given a `_execute` that returns 75 rows, `execute` returns exactly 50 rows with `truncated=True`; (3) error contract completeness — `ToolNotApplicable`, `InsufficientData`, and `RateLimited` each map to the correct `ToolErrorType` across at least one tool from each family; (4) tenant isolation — a tool called with `tenant_id=A` must never return rows scoped to `tenant_id=B`; each family tool has at least one test asserting the `tenant_id` predicate is included in the repository query. All tests use `pytest-asyncio` with `AsyncMock` for repositories and `fakeredis.aioredis` for Redis.

**Tests to write first (TDD):**
- `test_any_tool_second_call_same_run_id_returns_cached` — parameterised over one tool from each family
- `test_any_tool_75_rows_returns_50_truncated` — parameterised over one tool from each family
- `test_tool_not_applicable_maps_to_tool_error_tool_not_applicable`
- `test_insufficient_data_maps_to_tool_error_insufficient_data`
- `test_rate_limited_maps_to_tool_error_rate_limited_with_retry_after`
- `test_portfolio_tool_tenant_id_in_query`
- `test_company_tool_tenant_id_in_query`
- `test_events_tool_global_events_visible_to_all_tenants`
- `test_events_tool_other_tenant_events_not_returned`
- `test_macro_tool_tenant_id_in_query`
- `test_memory_tool_tenant_id_in_query`

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

## Acceptance Criteria Coverage

- AC-001: Given any tool call with parameters that would return more than 50 rows, the tool truncates to 50 rows and sets `truncated=True` → TASK-001, TASK-002, TASK-011
- AC-002: Given a tool called twice with identical arguments within the same workflow run, the second call returns the cached result without executing a new DB query or external API call → TASK-002, TASK-011
- AC-003: Given an external data source is rate-limited, the tool returns a `RateLimited` `ToolError` object (not an exception) → TASK-001, TASK-002, TASK-008, TASK-011
- AC-004: Given a tool invoked by an agent not authorized (enforced by agent YAML and `ToolGuard` from PLAN-F-011), a runtime guard raises `ToolNotApplicable` → TASK-002, TASK-003, TASK-010, TASK-011
- AC-005: Given all six tool families are implemented, each tool is accessible by name from the agent execution context and matches the tool identifier in agent YAMLs → TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010

## Risks and Notes

- `BaseTool.execute` uses an in-memory `run_cache` dict whose lifetime is the `WorkflowState` for a single run. The dict is passed by reference from `WorkflowState.tool_cache` (a new field the workflow executor must add). This means the caching guarantee only holds within one workflow run — not across runs. This is intentional per REQ-F-012.
- The 50-row hard limit in `ToolResult.from_rows` is applied after the repository returns data. Repository queries should ideally include a `LIMIT 51` (fetch one extra to detect truncation cheaply), but correctness must not depend on the repository respecting this hint — `ToolResult.from_rows` is the authoritative enforcement point.
- `GetEventsByCompany` and `GetEventExposure` must handle the `geo_event.tenant_id IS NULL` global-event visibility rule (Architecture §12.3). The SQL predicate is `(geo_event.tenant_id IS NULL OR geo_event.tenant_id = :tenant_id)`. Tests in TASK-006 and TASK-011 verify both branches.
- All tool `_execute` methods must call `CacheOrFetch.cache_or_fetch` from PLAN-F-032 — never a repository directly. The `CacheOrFetch` instance is injected into `BaseTool.__init__` and must not be constructed inside a tool class.
- TASK-010 extends `initialise_ai_module` from PLAN-F-011. The executor must read PLAN-F-011's `src/ai/startup.py` before modifying it, and must not break the existing `AgentRegistry` startup logic.
- Tool names are permanently public API identifiers referenced by agent YAML files. Renaming a tool after agent YAMLs are written requires updating both the Python class `name` attribute and every YAML `tools:` list that references it. The startup validation in TASK-010 catches any drift at process start.
- `GetEventAnalogies` delegates pgvector HNSW search to the `historical` module. At the time this plan is executed, the `historical` module interface may not yet exist (it depends on PLAN-F-004). The executor must define a minimal `IHistoricalSearch` protocol in `src/ai/tools/families/events_history.py` and inject it — do not import the concrete `historical` module class directly.
