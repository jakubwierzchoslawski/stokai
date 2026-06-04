# Requirements Index

> Auto-managed by `ba-requirements-gen`. Do not edit by hand.
> Last updated: 2026-06-02T00:00:00Z

## Summary

| Metric | Value |
|--------|-------|
| Total requirements | 48 |
| Functional | 33 |
| Non-functional | 15 |
| Status: draft | 48 |
| Status: approved | 0 |
| Domains processed | root |
| Open questions | 5 |

---

## Functional Requirements

| ID | Title | Complexity | TDD | Status | Source Docs |
|----|-------|-----------|-----|--------|-------------|
| [REQ-F-001](functional/REQ-F-001-reactive-pipeline-ingestion.md) | Reactive Pipeline Ingestion (Mode A) | XL | ✓ | draft | architectural-considerations-digest, system-description-digest |
| [REQ-F-002](functional/REQ-F-002-event-classification-and-extraction.md) | Event Classification and Extraction | M | ✓ | draft | architectural-considerations-digest |
| [REQ-F-003](functional/REQ-F-003-exposure-mapping.md) | Exposure Mapping | M | ✓ | draft | system-description-digest, architectural-considerations-digest |
| [REQ-F-004](functional/REQ-F-004-event-embedding-and-analogy-search.md) | Event Embedding and Analogy Search | M | ✓ | draft | architectural-considerations-digest |
| [REQ-F-005](functional/REQ-F-005-alert-dispatch-anti-fatigue.md) | Alert Dispatch and Anti-Fatigue | L | ✓ | draft | system-description-digest, ui-design-digest |
| [REQ-F-006](functional/REQ-F-006-morning-brief-workflow.md) | Morning Brief Workflow | XL | ✓ | draft | architectural-considerations-digest ⚠️ |
| [REQ-F-007](functional/REQ-F-007-on-demand-analysis-workflow.md) | On-Demand Analysis Workflow | L | ✓ | draft | architectural-considerations-digest |
| [REQ-F-008](functional/REQ-F-008-watchlist-scan-workflow.md) | Watchlist Scan Workflow | L | ✓ | draft | architectural-considerations-digest |
| [REQ-F-009](functional/REQ-F-009-earnings-risk-brief-workflow.md) | Earnings Risk Brief Workflow | L | ✓ | draft | architectural-considerations-digest |
| [REQ-F-010](functional/REQ-F-010-event-deep-dive-workflow.md) | Event Deep-Dive Workflow | L | ✓ | draft | architectural-considerations-digest |
| [REQ-F-011](functional/REQ-F-011-agent-registry-and-definitions.md) | Agent Registry and Definitions | L | ✓ | draft | architectural-considerations-digest |
| [REQ-F-012](functional/REQ-F-012-tool-library.md) | Tool Library | L | ✓ | draft | architectural-considerations-digest |
| [REQ-F-013](functional/REQ-F-013-hil-review-queue.md) | HIL Review Queue | L | ✓ | draft | architectural-considerations-digest, ui-design-digest |
| [REQ-F-014](functional/REQ-F-014-prompt-management-pipeline.md) | Prompt Management Pipeline | L | ✓ | draft | architectural-considerations-digest ⚠️ |
| [REQ-F-015](functional/REQ-F-015-four-layer-memory-subsystem.md) | Four-Layer Memory Subsystem | XL | ✓ | draft | architectural-considerations-digest ⚠️ |
| [REQ-F-016](functional/REQ-F-016-evaluation-framework.md) | Evaluation Framework (Tiers 1–3) | L | ✓ | draft | architectural-considerations-digest |
| [REQ-F-017](functional/REQ-F-017-scoring-engine-and-indicator-builder.md) | Scoring Engine and Indicator Builder | XL | ✓ | draft | system-description-digest, ui-design-digest |
| [REQ-F-018](functional/REQ-F-018-portfolio-scoring-and-geo-modifier.md) | Portfolio Scoring and Geo-Modifier | M | ✓ | draft | system-description-digest |
| [REQ-F-019](functional/REQ-F-019-intelligence-map.md) | Intelligence Map | XL | ✓ | draft | ui-design-digest, system-description-digest |
| [REQ-F-020](functional/REQ-F-020-progressive-disclosure-ui.md) | Progressive Disclosure UI | L | ✓ | draft | ui-design-digest |
| [REQ-F-021](functional/REQ-F-021-map-live-historical-playback-modes.md) | Map Live / Historical / Playback Modes | L | ✓ | draft | ui-design-digest, system-description-digest |
| [REQ-F-022](functional/REQ-F-022-screener.md) | Screener | M | ✓ | draft | ui-design-digest, system-description-digest |
| [REQ-F-023](functional/REQ-F-023-company-detail-and-on-demand.md) | Company Detail and On-Demand | M | ✓ | draft | ui-design-digest, system-description-digest |
| [REQ-F-024](functional/REQ-F-024-portfolio-and-watchlist-management.md) | Portfolio and Watchlist Management | M | ✓ | draft | system-description-digest, ui-design-digest |
| [REQ-F-025](functional/REQ-F-025-alerts-center.md) | Alerts Center | M | ✓ | draft | system-description-digest, ui-design-digest |
| [REQ-F-026](functional/REQ-F-026-briefs-reader.md) | Briefs Reader | M | ✓ | draft | ui-design-digest, architectural-considerations-digest |
| [REQ-F-027](functional/REQ-F-027-qa-chat-interface.md) | Q&A Chat Interface | M | ✓ | draft | ui-design-digest, architectural-considerations-digest |
| [REQ-F-028](functional/REQ-F-028-admin-data-source-management.md) | Admin: Data Source Management | L | ✓ | draft | ui-design-digest, system-description-digest |
| [REQ-F-029](functional/REQ-F-029-admin-ai-audit-console.md) | Admin: AI Audit Console | L | ✓ | draft | ui-design-digest, architectural-considerations-digest |
| [REQ-F-030](functional/REQ-F-030-admin-system-operations.md) | Admin: System Operations | L | ✓ | draft | ui-design-digest, architectural-considerations-digest |
| [REQ-F-031](functional/REQ-F-031-cold-start-data-seeding.md) | Cold-Start Data Seeding | L | ✓ | draft | system-description-digest ⚠️ |
| [REQ-F-032](functional/REQ-F-032-cache-or-fetch-data-access.md) | Cache-or-Fetch Data Access | M | ✓ | draft | system-description-digest |
| [REQ-F-033](functional/REQ-F-033-user-authentication-and-roles.md) | User Authentication and Roles | M | ✓ | draft | system-description-digest, ui-design-digest ⚠️ |

---

## Non-Functional Requirements

| ID | Title | NFR Category | Complexity | Status |
|----|-------|-------------|-----------|--------|
| [REQ-N-001](non-functional/REQ-N-001-mode-a-latency.md) | Mode A Pipeline Latency | Performance | M | draft |
| [REQ-N-002](non-functional/REQ-N-002-mode-b-latency.md) | Mode B Workflow Latency | Performance | M | draft |
| [REQ-N-003](non-functional/REQ-N-003-mode-a-cost.md) | Mode A Cost per Event | Reliability | M | draft |
| [REQ-N-004](non-functional/REQ-N-004-mode-b-cost.md) | Mode B Cost per Report | Reliability | M | draft |
| [REQ-N-005](non-functional/REQ-N-005-infrastructure-budget.md) | MVP Infrastructure Budget | Reliability | S | draft |
| [REQ-N-006](non-functional/REQ-N-006-multitenancy-security.md) | Multi-Tenancy and Security | Security | L | draft |
| [REQ-N-007](non-functional/REQ-N-007-portability-self-host.md) | Portability and Self-Hostability | Reliability | M | draft |
| [REQ-N-008](non-functional/REQ-N-008-ai-observability.md) | AI Observability | Observability | M | draft |
| [REQ-N-009](non-functional/REQ-N-009-prompt-regression-safety.md) | Prompt Regression Safety | Reliability | M | draft |
| [REQ-N-010](non-functional/REQ-N-010-ai-accuracy-calibration.md) | AI Accuracy Calibration | Reliability | M | draft |
| [REQ-N-011](non-functional/REQ-N-011-data-freshness.md) | Data Freshness and TTL Integrity | Reliability | M | draft |
| [REQ-N-012](non-functional/REQ-N-012-compliance-auditability.md) | Compliance and Auditability | Compliance | M | draft |
| [REQ-N-013](non-functional/REQ-N-013-accessibility.md) | Accessibility | Usability | M | draft |
| [REQ-N-014](non-functional/REQ-N-014-responsive-design.md) | Responsive Design | Usability | M | draft |
| [REQ-N-015](non-functional/REQ-N-015-scalability-cache.md) | Scalability via Cache | Scalability | M | draft |

---

## Needs Human Review ⚠️

These requirements have unresolved open questions and **must not be planned until resolved**.

| REQ | Open Question | Blocking? |
|-----|--------------|-----------|
| REQ-F-006 | What is the exact HIL timing window for Morning Brief? Is the 05:45 deadline hard regardless of user timezone? | Blocking for HIL scheduling logic |
| REQ-F-014 | What canary traffic percentage and duration are required before a prompt is eligible for promotion? | Blocking for canary implementation |
| REQ-F-015 | Who authors Layer 3 procedural memory v1 patterns, and what completeness criteria must be met before Phase 4 go-live? | Blocking for Phase 4 memory seeding |
| REQ-F-031 | Has the GDELT commercial license been verified for MVP production use? If denied, what is ACLED's coverage scope? | Blocking for provider selection |
| REQ-F-033 | What is the precise boundary between MVP username/password auth and OAuth2? When does OAuth2 migration trigger? | Non-blocking for MVP; informational for post-MVP planning |

---

## Traceability Matrix

| Source Document | Derived Requirements |
|-----------------|---------------------|
| `docs/kb/architectural_considerations.md` | REQ-F-001, REQ-F-002, REQ-F-004, REQ-F-006, REQ-F-007, REQ-F-008, REQ-F-009, REQ-F-010, REQ-F-011, REQ-F-012, REQ-F-013, REQ-F-014, REQ-F-015, REQ-F-016, REQ-F-026, REQ-F-027, REQ-F-029, REQ-F-030, REQ-N-001, REQ-N-002, REQ-N-003, REQ-N-004, REQ-N-007, REQ-N-008, REQ-N-009, REQ-N-010, REQ-N-011 |
| `docs/kb/system_description.md` | REQ-F-001, REQ-F-003, REQ-F-005, REQ-F-018, REQ-F-022, REQ-F-023, REQ-F-024, REQ-F-025, REQ-F-028, REQ-F-031, REQ-F-032, REQ-F-033, REQ-N-001, REQ-N-004, REQ-N-005, REQ-N-006, REQ-N-007, REQ-N-011, REQ-N-012, REQ-N-015 |
| `docs/kb/ui_design.md` | REQ-F-005, REQ-F-013, REQ-F-017, REQ-F-019, REQ-F-020, REQ-F-021, REQ-F-022, REQ-F-023, REQ-F-024, REQ-F-025, REQ-F-026, REQ-F-027, REQ-F-028, REQ-F-029, REQ-F-030, REQ-F-033, REQ-N-013, REQ-N-014 |

---

## Dependency Notes

Key implementation order constraints (non-exhaustive):

- **REQ-F-033** (auth) must precede any requirement with user/tenant context
- **REQ-F-032** (cache-or-fetch) is a cross-cutting concern depended on by REQ-F-001, REQ-F-002, REQ-F-003, REQ-F-004
- **REQ-F-031** (cold-start seeding) must complete before REQ-F-004 (analogy search) is useful
- **REQ-F-011** + **REQ-F-012** (agent registry + tool library) are prerequisites for REQ-F-006 through REQ-F-010
- **REQ-F-015** (memory subsystem) must be in place before REQ-F-006 through REQ-F-010 go to production
- **REQ-F-016** (evaluation framework) must deploy alongside REQ-F-006 (Morning Brief) per Phase 4 mandate
- **REQ-F-017** (scoring engine) is a prerequisite for REQ-F-006, REQ-F-008, REQ-F-019
- **REQ-F-001** (Mode A pipeline) is a prerequisite for REQ-F-010 (Event Deep-Dive enqueue trigger)
- **REQ-F-028** (admin data sources) must precede any provider configuration (REQ-F-001 runtime config)
- **REQ-F-019** (intelligence map) depends on REQ-F-001 (events), REQ-F-017 (scores), REQ-F-032 (cache)
