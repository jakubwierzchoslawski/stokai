---
req_id: REQ-F-012
slug: tool-library
title: Agent Tool Library
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "cache-or-fetch-data-access: Tool library relies on cache-or-fetch pattern for data retrieval" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, tools, data-access]
  story_points:
  components: [tool-library, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Agent Tool Library

## Domain Context
The Tool Library is the scoped, bounded abstraction layer between agents and all data sources. Agents never access the database or external APIs directly — all data access flows through this library. Tools enforce bounded output (max 50 rows) and a standard error contract.

## Summary
The system must implement a Tool Library providing six families of tools (portfolio context, company data, events + history, exposure + correlation, macro + market, memory + track record), each with bounded output (max 50 rows), a standard error contract (ToolNotApplicable / InsufficientData / RateLimited), and per-workflow-run result caching.

## Detailed Description
As specified in architectural-considerations-digest.md §Business Rules items 31–32 and §Architecture Signals, the Tool Library is the hard boundary between agents and data. The six tool families are:

**Portfolio Context Tools:**
- get_portfolio_positions(user_id) → positions with tickers, shares, cost basis
- get_watchlist(user_id) → watchlist companies
- get_scoring_profile(user_id) → active scoring profile

**Company Data Tools:**
- get_company_fundamentals(ticker) → fundamentals data
- get_company_scores(company_id, profile_id) → current scores with breakdown
- get_price_history(ticker, from_date, to_date, interval) → OHLCV bars

**Events + History Tools:**
- get_events_by_company(company_id, from_date, to_date) → geo_events
- get_event_analogies(event_id, top_k) → historical analogies
- get_ai_recommendation_history(company_id) → past recommendations

**Exposure + Correlation Tools:**
- get_event_exposure(event_id) → exposure rows for event
- get_company_exposure_history(company_id) → past exposure records

**Macro + Market Tools:**
- get_macro_indicators(indicator_list) → FRED/World Bank data
- get_sector_performance(sector, from_date, to_date) → sector metrics

**Memory + Track Record Tools:**
- get_semantic_facts(entity_id) → semantic memory facts
- get_procedural_patterns(context_tags) → relevant procedural patterns
- get_recommendation_outcomes(company_id) → past recommendation accuracy

All tools must:
- Return at most 50 rows
- Use the standard error contract: ToolNotApplicable (tool cannot apply to query), InsufficientData (not enough data available), RateLimited (external source rate-limited)
- Cache results per workflow run (same tool + arguments returns cached result within same run)

## Desired Outcome
Every agent in every workflow accesses data exclusively through tool calls, with bounded, predictable outputs and consistent error handling, enabling deterministic testing and preventing unbounded data consumption.

## Acceptance Criteria
- [ ] AC-001: Given any tool call with parameters that would return more than 50 rows, the tool truncates or paginates the result to 50 rows maximum and includes a truncation indicator in the response.
- [ ] AC-002: Given a tool is called twice with identical arguments within the same workflow run, the second call returns the cached result without executing a new DB query or external API call.
- [ ] AC-003: Given an external data source is rate-limited, the tool returns a RateLimited error object (not an exception) following the standard error contract, allowing the agent to handle gracefully.
- [ ] AC-004: Given a tool is invoked by an agent not listed as an authorized user of that tool (enforced by agent YAML), a runtime guard raises ToolNotApplicable error rather than executing.
- [ ] AC-005: Given all six tool families are implemented, each tool is accessible by name from the agent execution context and the tool name matches the tool identifier listed in agent YAMLs.

## Out of Scope
- Tools for Phase 2/3 integrations (push notifications, broker)
- Direct database access bypassing the tool library (forbidden by architecture)
- Tool implementations that call external APIs without going through the cache-or-fetch layer

## Data Models
```
ToolResult:
  data: list[dict]  -- max 50 items
  truncated: bool
  row_count: int

ToolError:
  error_type: enum(ToolNotApplicable, InsufficientData, RateLimited)
  message: string
  retry_after: int | null  -- seconds, for RateLimited

ToolCacheEntry (per workflow run):
  run_id: UUID
  tool_name: string
  args_hash: string
  result: ToolResult
  cached_at: timestamp
```

## Process Sequence
1. Agent node resolves tool by name from its YAML tools list
2. Tool cache checked for (run_id, tool_name, args_hash)
3. Cache hit: return cached ToolResult
4. Cache miss: execute data access via cache-or-fetch layer (Redis → PostgreSQL → external API)
5. Result bounded to 50 rows; truncation flag set if needed
6. Error conditions mapped to standard ToolError contract
7. Result cached for current workflow run; returned to agent

## Subtasks
- [ ] ST-001: Implement Tool base class with cache, bounds, and error contract — complexity: M
- [ ] ST-002: Implement Portfolio Context tool family (3 tools) — complexity: M
- [ ] ST-003: Implement Company Data tool family (3 tools) — complexity: M
- [ ] ST-004: Implement Events + History tool family (3 tools) — complexity: M
- [ ] ST-005: Implement Exposure + Correlation tool family (2 tools) — complexity: S
- [ ] ST-006: Implement Macro + Market tool family (2 tools) — complexity: M
- [ ] ST-007: Implement Memory + Track Record tool family (3 tools) — complexity: M
- [ ] ST-008: Unit tests for all tools including cache hit, bounds enforcement, error contract — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 31-32; §Architecture Signals | Max 50 rows, error contract (ToolNotApplicable/InsufficientData/RateLimited), per-run cache, tool families |
| system-description-digest.md | §Architecture Signals | All backend modules interact through provider adapter interfaces; direct API calls forbidden |
