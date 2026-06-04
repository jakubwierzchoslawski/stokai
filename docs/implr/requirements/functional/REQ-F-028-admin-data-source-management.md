---
req_id: REQ-F-028
slug: admin-data-source-management
title: Admin Data Source Management
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - ui-design-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "user-authentication-and-roles: Admin/operator role required to access admin panel" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, frontend, admin, data-sources]
  story_points:
  components: [admin-panel, data-sources]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Admin Data Source Management

## Domain Context
All data sources are managed via the admin panel with no code deploy required. The source_config and market_source_binding tables (DB-backed from day one per C-004 resolved) are the authoritative configuration. Twitter/X is off by default (C-006 resolved). Social stubs are listed and toggleable.

## Summary
The system must provide an admin panel screen to list all data providers with health/cost/last-fetch status, enable/disable any source without code deploy, add providers by setting credentials and config, assign primary/fallback binding per market per interface, and toggle social sources (Twitter/X off by default).

## Detailed Description
As specified in ui-design-digest.md business rules 38–45 and system-description-digest.md business rules 9, 11:

**Source List:**
- All configured sources listed with: display_name, interface_type, enabled status, health indicator, last_fetch timestamp, cost_tier, calls_today, rate_limit_pct, errors_today, estimated_cost

**Enable/Disable:**
- Toggle switches on each source
- Disabling automatically routes to the configured fallback (market_source_binding.role=fallback)
- Takes effect at runtime without code deploy or restart

**Add Provider:**
- Form: display_name, interface_type, credentials_ref (vault reference, never plaintext), config (JSONB), cost_tier, priority
- Adapter code must exist in the codebase; configuration activates it

**Market-to-Source Binding:**
- Admin sets which source serves which market for which interface type (primary/fallback)
- Stored in market_source_binding table
- Refreshed at runtime (no restart required)

**Social Sources:**
- StockTwits, Reddit, Telegram, Truth Social, Twitter/X all listed
- Twitter/X is off by default; requires explicit admin toggle to enable (C-006 resolved)
- Each shows: status, enable/disable toggle, last-fetch, cost tier

**Per-Source Health Dashboard:**
- calls_today, rate_limit_pct_used, error_count, estimated_cost_today
- Alert threshold visible (e.g. rate limit > 80%)

## Desired Outcome
Operators can add, configure, enable, and disable any data source at runtime through the admin panel without writing code or restarting services, with full visibility into each source's health and cost.

## Acceptance Criteria
- [ ] AC-001: Given an admin disables a data source, the system immediately routes all affected data requests to the configured fallback source; the primary source receives no further API calls until re-enabled, with no code deployment required.
- [ ] AC-002: Given an admin adds a new source with a credentials_ref (vault reference) and config, the source appears in the list in disabled state; enabling it begins using it for data fetching without a restart.
- [ ] AC-003: Given Twitter/X is listed in the social sources section, it appears with enabled=false by default; an admin must explicitly toggle it on to activate it.
- [ ] AC-004: Given an admin changes the market_source_binding (reassigning primary/fallback for a market/interface), the change takes effect within 60 seconds without a service restart.
- [ ] AC-005: Given an end-user attempts to access the admin data source management endpoint, the response is HTTP 403 Forbidden.

## Out of Scope
- Writing adapter code from the admin panel (code must exist first)
- Automated provider discovery
- Self-provisioning of external API credentials (vault management is external)

## Data Models
```
source_config:
  source_id: UUID (PK)
  interface_type: string  -- e.g. PriceProvider, NewsProvider
  display_name: string
  enabled: bool
  credentials_ref: string  -- vault path, never plaintext
  config: JSONB
  cost_tier: string
  priority: int
  updated_at: timestamp

market_source_binding:
  market_id: UUID (FK → market)
  interface_type: string
  source_id: UUID (FK → source_config)
  role: enum(primary, fallback)
  PK: (market_id, interface_type, source_id)
```

## Process Sequence
1. Admin navigates to data source management panel
2. List loads from source_config table
3. Admin toggles enable/disable → source_config.enabled updated; routing updated immediately
4. Admin adds new source → form submitted → source_config row created (enabled=false)
5. Admin updates market binding → market_source_binding row updated; routing refreshed
6. Health dashboard: queries from last 24 h aggregated per source

## Subtasks
- [ ] ST-001: Implement source_config and market_source_binding tables (C-004 resolved: DB-backed from day one) — complexity: M
- [ ] ST-002: Implement source list and health API endpoint — complexity: M
- [ ] ST-003: Implement enable/disable with immediate fallback routing — complexity: M
- [ ] ST-004: Implement add-provider form and API — complexity: M
- [ ] ST-005: Implement market binding management UI and API — complexity: M
- [ ] ST-006: Implement social sources section with Twitter/X off-by-default — complexity: S
- [ ] ST-007: Frontend admin data source management panel — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | Business Rules 38-45; System Behaviours Required; Data Entities (source_config, market_source_binding) | All admin data source requirements, DB-backed registry (C-004 resolved), Twitter/X off by default (C-006 resolved) |
| system-description-digest.md | Business Rules 9, 11 | No hardcoding of providers, Twitter/X free API off-by-default |
