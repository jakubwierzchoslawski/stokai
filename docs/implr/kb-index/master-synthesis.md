---
domains_included: [root]
synthesised_at: 2026-06-02T00:00:00Z
kb_total_files: 3
master_checksum: ac023544fecfddfc722280847d056505
---

# Master Synthesis

## System Overview

StokAI is a geopolitical intelligence platform for retail investors, built around a world map as the primary decision interface. The core value proposition is compressing 20–40 minutes of manual analyst synthesis into 90 seconds: when a geopolitical event occurs, the system automatically identifies which portfolio companies are affected, retrieves historical analogies, and produces a confidence-scored action recommendation — all before the average retail investor hears about it.

The system operates across two fundamentally different execution modes. Mode A (Reactive Pipeline) is a deterministic, fixed-step sequence that converts real-time events (tweets, GDELT polls, SEC filings, price anomalies) into alerts within 90 seconds at $0.05 per event. Mode B (Deliberative Workflows) is a LangGraph-orchestrated agentic system where named-role agents (Relevance Analyst, Recommendation Synthesizer, Narrative Writer, and six others) produce deep analytical reports via scheduled or on-demand workflows, targeting 2–5 minutes and $0.50–$2.00 per report. The two modes share a single database, memory subsystem, tool library, and observability stack (Langfuse, self-hosted).

The architecture is built on five immutable principles: everything behind an interface (provider, market, and database abstraction); local-first data (cache-or-fetch with TTLs, external APIs as last resort); multi-tenant schema from day 1 (tenant_id on every user table); containerized and portable (Docker/K8s, no hard Azure lock-in); and transparent AI (every recommendation carries confidence, sample size, and a traceable "why"). The entire system — including all data sources — is configurable through an admin panel, with no hardcoded provider selections.

## Domain Map

| Domain | Files | Key Entities | Contradictions | NFR Signals | Arch Files |
|--------|-------|--------------|---------------|-------------|-----------|
| root | 3 | geo_event, company, price_bar, event_exposure, event_embedding, ai_recommendation, company_score, indicator, workflow_run, agent_invocation, semantic_fact, user_feedback, WorkflowState, MarketConfig | 6 | 27 | 3 |

## Cross-Domain Contradictions

All contradictions are intra-domain (root). No cross-domain contradictions applicable (single domain KB).

| ID | Description | Domain A | Source A | Domain B | Source B | Type |
|----|-------------|---------|---------|---------|---------|------|
| C-001 | Morning Brief trigger time: 05:30 vs 06:00 | root | architectural_considerations.md | root | system_description.md | Hard conflict |
| C-002 | Total MVP cost: $430–520/month vs $268/month | root | architectural_considerations.md | root | system_description.md | Hard conflict |
| C-003 | Classification LLM: Claude Haiku 4.5 vs Azure OpenAI GPT-4o-mini | root | architectural_considerations.md | root | system_description.md | Soft conflict |
| C-004 | MARKET_REGISTRY: code dict vs DB-backed admin-editable table | root | system_description.md | root | ui_design.md | Soft conflict |
| C-005 | Reactive Pipeline step count: 12 (body) vs 13 (Decision Summary header) | root | architectural_considerations.md | root | architectural_considerations.md | Scope overlap |
| C-006 | Twitter/X: primary real-time pipeline trigger vs off-by-default admin toggle | root | architectural_considerations.md | root | ui_design.md | Scope overlap |

## Global NFR Candidates

| Category | Frequency | Domains |
|----------|-----------|---------|
| Latency / Performance | 3 | root |
| Cost / Budget | 3 | root |
| Compliance / Auditability | 2 | root |
| Security / Multitenancy | 2 | root |
| Portability / Self-hostability | 2 | root |
| Flexibility / Configurability | 2 | root |
| Observability | 2 | root |
| Reliability / Resilience | 2 | root |
| Scalability / Cost | 2 | root |
| Quality / Regression Safety | 1 | root |
| Accuracy / Calibration | 1 | root |
| Data Freshness / Integrity | 1 | root |
| Accessibility | 1 | root |
| Responsive Design | 1 | root |
| UX Responsiveness | 1 | root |
| Data Retention | 1 | root |
| Operational Configurability | 1 | root |

## Architecture-Relevant Files

| File | Domain | Relevance | Reason |
|------|--------|-----------|--------|
| docs/kb/architectural_considerations.md | root | explicit | doc_type: architecture — StokAI Agentic Architecture specification |
| docs/kb/system_description.md | root | explicit | doc_type: architecture — StokAI Master Architecture Document |
| docs/kb/ui_design.md | root | auto | Contains significant architectural signals: frontend stack mandate (React 18, MapLibre, Supercluster, TanStack Query), DB migration requirement (provider_registry/MARKET_REGISTRY to DB-backed service), admin panel data model (source_config, market_source_binding tables), and adapter pattern specification |

## Open Ambiguities

- **C-001 unresolved**: Morning Brief trigger time — 05:30 (architectural_considerations) vs 06:00 (system_description). Scheduling implementation blocked until resolved.
- **C-002 unresolved**: Total MVP cost — $430–520/month vs $268/month. Itemised breakdown inconsistent with both figures. Detailed cost model required before infrastructure planning.
- **C-003 unresolved**: Classification LLM — Claude Haiku 4.5 vs Azure OpenAI GPT-4o-mini (VNet-isolated). Contradiction decision log (project memory C-001–C-006) references a "multi-provider LLM" decision; documents do not reflect the resolved state.
- **C-004 unresolved**: MARKET_REGISTRY persistence — code dict (current) vs DB-backed admin table (ui_design requirement). Migration scope and timing undecided.
- **C-005 unresolved**: Reactive Pipeline step count — 12 steps enumerated in body vs 13 cited in Decision Summary header (same document). Must resolve before implementation to avoid off-by-one error.
- **C-006 unresolved**: Twitter/X treatment — primary real-time trigger in architectural_considerations vs off-by-default admin toggle in ui_design. MVP implementation choice needed.
- **Twitter/X free tier**: Memory references "free Twitter/X" but Filtered Stream has no documented free tier at required volume; exact endpoint and access mechanism unverified.
- **GDELT license**: Commercial use for MVP unverified; ACLED designated fallback but coverage scope unspecified.
- **Canary parameters**: Canary traffic percentage and duration for prompt promotion are undefined.
- **HIL timing windows**: Referenced in architectural_considerations but no specific values provided for any workflow.
- **~100–200 tracked companies**: Soft figure; hard upper limit and criteria for on-demand → tracked promotion undefined.
- **CONTRARIAN signal definition**: Conditions distinguishing CONTRARIAN from HEDGE are unspecified.
- **Score history retention**: Granularity, retention period, and storage strategy for Historical mode time-machine unspecified.
- **OAuth2 scope**: MVP username/password vs OAuth2 boundary undefined.
- **ui_design.md finality**: Document self-flags as a proposal that "should be rethought" — UI specification scope is unresolved.
- **Model IDs forward-dated**: "Claude Opus 4.7" and "Claude Sonnet 4.6" appear in May 2026 docs; unclear if placeholder names or confirmed model IDs.
