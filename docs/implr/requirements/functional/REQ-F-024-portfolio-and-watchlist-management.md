---
req_id: REQ-F-024
slug: portfolio-and-watchlist-management
title: Portfolio and Watchlist Management
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - ui-design-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "user-authentication-and-roles: User identity required before portfolio can be created" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, frontend, portfolio, onboarding]
  story_points:
  components: [portfolio, frontend]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Portfolio and Watchlist Management

## Domain Context
Portfolio and watchlist are foundational — without them the map shows no portfolio context, no scoring overlays, and no personalized alerts. The first-run guided onboarding with preset scoring profiles prevents the empty-map bounce problem.

## Summary
The system must provide portfolio and watchlist management with manual entry (ticker + shares + cost basis) and CSV import; a guided first-run onboarding that offers preset scoring profiles; and an empty watchlist state that prompts users to add companies.

## Detailed Description
As specified in ui-design-digest.md §Business Rules items 23–24, 36–37 and system-description-digest.md §Business Rules item 23:

**Portfolio Management:**
- Manual entry: ticker, number of shares, cost basis (optional)
- CSV import: ticker, shares, cost_basis columns; validation with error report
- Multiple portfolios per user (for multi-account support)
- Each position carries: company_id (resolved from ticker), shares, cost_basis, added_at, source (manual | csv | broker)
- Broker connection deferred to Phase 3 (Interactive Brokers)

**Watchlist:**
- List of tickers (no position data required)
- Empty watchlist: show guided prompt "Add companies to see geopolitical events affecting your holdings"

**Guided First-Run Onboarding:**
- Triggered on first login when portfolio is empty
- Step 1: Choose a preset scoring profile (Value Investor / Growth Hunter / Macro Aware)
- Step 2: Add first holdings (manual or CSV)
- Step 3: Preview how map changes with portfolio context active
- Prevents empty-map bounce: user cannot reach map until at least one holding is added OR explicitly skips

**User Settings Integration:**
- Anti-fatigue controls (daily alert limit, quiet hours, per-ticker thresholds)
- Notification channels (email, push phase 2)
- Default scoring profile

## Desired Outcome
New users are guided through portfolio setup before reaching the map, preventing confusion from an empty map, and all users can easily manage their holdings with flexible input methods.

## Acceptance Criteria
- [ ] AC-001: Given a first-time user logs in with an empty portfolio, the onboarding flow is presented offering three preset scoring profiles; the user cannot navigate directly to the map until they add at least one holding or explicitly click "Skip".
- [ ] AC-002: Given a user manually enters a ticker, shares, and cost basis, a portfolio position is created and the company appears in the map's portfolio overlay context.
- [ ] AC-003: Given a user uploads a CSV file with ticker, shares, and cost_basis columns, valid rows create positions; invalid rows produce a per-row error report without blocking valid rows.
- [ ] AC-004: Given the watchlist is empty, the watchlist section displays a guided prompt to add companies, not a blank state.
- [ ] AC-005: Given a user deletes a position, the position is removed and the map overlay updates to exclude that company from portfolio context.

## Out of Scope
- Broker integration (Interactive Brokers deferred to Phase 3)
- Real-time portfolio valuation (scores are custom, not market value)
- Tax lot management

## Data Models
```
portfolio:
  portfolio_id: UUID
  tenant_id: UUID
  user_id: UUID
  name: string
  created_at: timestamp

position:
  position_id: UUID
  portfolio_id: UUID
  company_id: UUID
  ticker: string
  shares: float
  cost_basis: float | null
  added_at: timestamp
  source: enum(manual, csv, broker)

watchlist_item:
  item_id: UUID
  user_id: UUID
  company_id: UUID
  ticker: string
  added_at: timestamp
```

## Process Sequence
1. First login: onboarding flow → select profile → add holdings → preview map
2. Manual add: POST /portfolio/positions with ticker, shares, cost_basis
3. CSV import: POST /portfolio/import with CSV; validate → create valid positions; return error report for invalid
4. Watchlist add: POST /watchlist with ticker
5. Map context updated after any portfolio change

## Subtasks
- [ ] ST-001: Implement portfolio and position CRUD API — complexity: M
- [ ] ST-002: Implement CSV import with validation and error reporting — complexity: M
- [ ] ST-003: Implement guided first-run onboarding UI flow — complexity: M
- [ ] ST-004: Implement watchlist CRUD and empty-state prompt — complexity: S
- [ ] ST-005: Implement portfolio context propagation to map overlay — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | §Business Rules items 23-24, 36-37 | Empty watchlist prompt, onboarding, user settings integration |
| system-description-digest.md | §Business Rules item 23 | Guided first-run, preset scoring profiles, prevent empty-map bounce |
