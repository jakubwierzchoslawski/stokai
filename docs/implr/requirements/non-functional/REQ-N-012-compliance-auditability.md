---
req_id: REQ-N-012
slug: n-compliance-auditability
title: AI Compliance and Auditability
type: non-functional
nfr_category: Compliance
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "four-layer-memory-subsystem: Layer 1 episodic stores AI reasoning steps" }
  - { id: "", reason: "admin-ai-audit-console: Admin can replay full reasoning chain" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, compliance, audit, legal]
  story_points:
  components: [audit, compliance]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — AI Compliance and Auditability

## Domain Context
Every AI reasoning step must be stored for audit. The system operates on derived data, not raw prices, to manage data redistribution risk. Legal disclaimers must appear when historical sample size is small. Ex-post accuracy is tracked and visible to users.

## Summary
Every AI reasoning step must be stored in the DB with indefinite retention. Admins must be able to replay the full reasoning chain for any decision. Legal disclaimers must appear when sample_size < 5. Ex-post accuracy must be tracked and visible to users. System must operate on derived data only.

## Detailed Description
As specified in architectural-considerations-digest.md business rule 11 and system-description-digest.md business rules 3, 5, 21:

**Mandatory AI reasoning storage:** Every agent invocation, tool call, and LLM call within any workflow stores a row in the corresponding episodic memory table (agent_invocation, tool_call). These rows are append-only and indefinitely retained.

**Admin replay:** For any AI decision, an admin can replay the full reasoning chain by retrieving the Langfuse trace + episodic memory rows. The admin AI audit console implements this as a step-through view.

**Legal disclaimers:**
- When sample_size < 5 in any recommendation output, the disclaimer "Based on fewer than 5 historical cases — treat with caution" must appear inline in every display surface (alert, side panel, brief, email).
- Recommendations are explicitly framed as decision frameworks, not transaction signals; no language implying buy/sell obligation.

**Ex-post accuracy visibility:**
- actual_t1d and actual_t1w accuracy visible in the admin calibration dashboard
- Recommendation track record accessible from Company Detail screen (per ui-design-digest.md)

**Derived data only:** The system stores and operates on derived data (scores, analyses, recommendations) not raw licensed price data. This is an architectural constraint to manage data redistribution risk.

## Desired Outcome
Any AI decision can be fully audited by an admin, all legal disclosure requirements are met on every output surface, and the system's data handling strategy does not trigger data redistribution licensing violations.

## Acceptance Criteria
- [ ] AC-001: Given any agent invocation in any workflow, an agent_invocation row is present in PostgreSQL within 5 seconds of the invocation completing, with all required fields (workflow_run_id, agent_role, prompt_version, cost_usd, confidence).
- [ ] AC-002: Given an admin selects any AI decision in the audit console and clicks "Replay", all tool calls and intermediate outputs for that decision are displayed in chronological step-through order.
- [ ] AC-003: Given any display surface (alert text, side panel, email, brief) shows a recommendation with sample_size < 5, the disclaimer text is present and visible without requiring user interaction to reveal it.
- [ ] AC-004: Given a search of the application codebase and database for raw OHLCV price data served to end users, only derived representations (scores, sparklines, percentile ranks) are found; raw redistributable price data is not exposed.

## Out of Scope
- Legal review of disclaimer language (provided by legal counsel; displayed as-is)
- MiFID II / SEC investment adviser registration (product is educational, not regulated advice)

## NFR-Specific Fields

### Measurable Target
- AI reasoning storage: 100% of agent invocations produce agent_invocation rows (verified by row count = invocation count over 24-hour windows)
- Disclaimer compliance: 100% of recommendations with sample_size < 5 display the disclaimer (verified by automated UI test)
- Admin replay coverage: full reasoning chain available for 100% of decisions in the last 90 days

### Verification Method
- Method: Automated test asserting agent_invocation row presence after workflow execution; UI test asserting disclaimer visibility; DB audit for raw price data exposure
- Tool/Process: pytest integration tests; Playwright UI tests for disclaimer; DB query inspection
- Frequency: Per release (tests); continuous (row count monitoring)
- Owner: QA / Legal / DevOps

### Category Rationale
Compliance NFR because AI recommendation systems face increasing regulatory scrutiny. Auditability enables the operator to demonstrate due diligence; disclaimers manage legal liability; derived-data-only prevents data licensing violations.

## Subtasks
- [ ] ST-001: Implement insert-only enforcement on agent_invocation and tool_call tables — complexity: S
- [ ] ST-002: Implement disclaimer injection for sample_size < 5 on all display surfaces — complexity: M
- [ ] ST-003: Implement admin reasoning chain replay view — complexity: M
- [ ] ST-004: Automated tests for disclaimer presence and agent_invocation completeness — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Business Rule 11; Non-Functional Signals | Every AI reasoning step stored, override feedback loop |
| system-description-digest.md | Business Rules 3, 5, 21; Non-Functional Signals | Confidence + sample_size always visible, disclaimer when <5 analogies, derived data only |
