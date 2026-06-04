---
req_id: REQ-F-030
slug: admin-system-operations
title: Admin System Operations Panel
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "admin-data-source-management: Data source controls overlap with ingestion job management" }
  - { id: "", reason: "hil-review-queue: HIL queue management is part of admin system operations" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [backend, frontend, admin, operations]
  story_points:
  components: [admin-panel, operations]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Admin System Operations Panel

## Domain Context
The admin system operations panel aggregates operational controls: ingestion job status and manual triggers, cost monitoring vs budget, tracked company universe management, cache inspection, and feature flag toggles.

## Summary
The system must provide admin system operations covering: ingestion job status + manual trigger, cost monitor vs budget with per-source/model/workflow breakdown and threshold alerts, tracked company universe management (~100–200 companies), cache inspection and force-refresh, and feature flag toggles per environment.

## Detailed Description
As specified in ui-design-digest.md business rules 52, 55–58:

**Ingestion Jobs:**
- List: all scheduled ingestion jobs with name, schedule, last_run, next_run, status, error_count
- Manual trigger button per job
- Failures listed with stack trace access

**Cost Monitor:**
- Aggregate spend vs daily/monthly budget threshold
- Alert at 80% of budget; hard-stop indicator at 100%
- Breakdown by: source, model (Haiku/Sonnet/Opus), workflow type
- Per-source cost chart (last 30 days)
- Budget threshold configurable from admin panel (target: AI + infra < $100/month per C-002 resolved)

**Tracked Company Universe:**
- List ~100–200 tracked companies with market cap, sector, status
- Promote on-demand company to tracked status
- Remove company from tracked (changes is_tracked flag; does not delete history)

**Cache Inspection:**
- View storage size by data type (price bars, embeddings, event data)
- Force-refresh: clear cache for specific company or data type
- Storage growth chart (last 30 days)

**Feature Flags:**
- Toggle per-environment: real-time mode (WebSocket vs polling), specific workflows (enable/disable Morning Brief, Watchlist Scan, etc.), social sources (Twitter/X, StockTwits, etc.)
- Changes apply at runtime without restart

## Desired Outcome
Operators have full runtime control over system behaviour, costs, and data coverage without requiring code deployments, and can respond immediately to operational issues or budget overruns.

## Acceptance Criteria
- [ ] AC-001: Given an admin clicks "Manual Trigger" on an ingestion job, the job is dispatched immediately to the Celery queue and the job status updates to "running" within 5 seconds.
- [ ] AC-002: Given aggregate AI + infrastructure spend reaches 80% of the configured budget threshold, the cost monitor displays a warning alert; at 100% it displays a hard-stop indicator and no further AI-cost-incurring workflows are dispatched.
- [ ] AC-003: Given an admin promotes an on-demand company to tracked status, the company's is_tracked flag is set to true and it is included in subsequent ingestion, scoring, and exposure mapping runs.
- [ ] AC-004: Given an admin force-refreshes the cache for a specific data type, the next data access for that type fetches fresh data from the external source rather than returning the cached value.
- [ ] AC-005: Given an admin toggles the "Morning Brief" feature flag to disabled, no Morning Brief Celery tasks are dispatched on subsequent cron fires until the flag is re-enabled.

## Out of Scope
- Infrastructure provisioning from the admin panel (add/remove servers)
- Database migration execution from the admin panel

## Data Models
```
IngestionJob:
  job_id: UUID
  name: string
  schedule: cron_expression
  last_run: timestamp
  next_run: timestamp
  status: enum(idle, running, failed)
  error_count: int

CostRecord:
  date: date
  source: string
  model: string | null
  workflow_type: string | null
  cost_usd: float

FeatureFlag:
  flag_id: string
  environment: string
  enabled: bool
  updated_at: timestamp
  updated_by: UUID
```

## Process Sequence
1. Admin navigates to System Operations panel
2. Ingestion jobs loaded; admin clicks Manual Trigger → Celery task dispatched
3. Cost monitor loaded with current spend vs budget threshold
4. Admin reviews tracked companies; promotes/demotes as needed
5. Admin inspects cache; force-refreshes specific entries
6. Admin toggles feature flags; changes applied at runtime

## Subtasks
- [ ] ST-001: Implement ingestion job list and manual trigger API — complexity: M
- [ ] ST-002: Implement cost monitoring with threshold alerts — complexity: M
- [ ] ST-003: Implement tracked company universe management API — complexity: S
- [ ] ST-004: Implement cache inspection and force-refresh API — complexity: M
- [ ] ST-005: Implement feature flag store and runtime toggle — complexity: M
- [ ] ST-006: Frontend admin system operations panel — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | Business Rules 52, 55-58 | Ingestion jobs, cost monitor, tracked universe, cache management, feature flags |
