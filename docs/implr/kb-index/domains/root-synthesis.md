---
domain: root
source_digests:
  - { file: architectural_considerations.md, checksum: eb14e952c74f04a1c44f12aee13ecc55 }
  - { file: system_description.md, checksum: 18189a5fc42d3b090a14b67fdd9eb23e }
  - { file: ui_design.md, checksum: 658153c855e3b69bc90624b223744025 }
synthesised_at: 2026-06-02T00:00:00Z
synthesis_checksum: b3c2e7a1f94d6e08a5b2c9d3f1e74a62
---

# Domain Synthesis: Root

## Unified Business Rules

### System Identity and Scope
1. StokAI interprets what world events mean for portfolio companies; it does not merely report what happened.
2. Target information edge: alerts 20–90 minutes ahead of the average retail investor.
3. Recommendations are decision frameworks, not transaction signals; no buy/sell execution is implied.
4. No autonomous trading, no open-ended exploration, no multi-agent debate, and no prompt-injection surface are permitted.
5. Starting market is US only (NYSE + NASDAQ); additional markets are added via configuration only, never code changes.
6. Company analysis scope is approximately 100–200 tracked companies; additional companies are fetchable on demand.
7. Legal: system operates on derived data (scores, analyses), not raw prices, to manage data redistribution risk.
8. Cold-start requirement: GDELT historical archive (1979+) must be seeded with historical prices so the analogy engine is functional at launch.

### Operating Modes
9. The system operates in exactly two modes: Reactive Pipeline (Mode A) and Deliberative Workflows (Mode B); no hybrid or fallback mode is defined.
10. Mode A is triggered by external events (Tweet, GDELT poll, SEC EDGAR filing, price anomaly) and must complete within 90 seconds at a cost ceiling of $0.05 per event.
11. Mode B is triggered by cron schedule, user request, Mode A event, or watchlist alarm, with a cost ceiling of $0.50–$2.00 per report and a latency target of 2–5 minutes.
12. The Reactive Pipeline is a fixed-step sequence (12 numbered steps) with no tools, no loops, and no decision branches.
13. A deep-dive Mode B job is enqueued if event intensity >= 4 or a portfolio match is detected in the final pipeline step.
14. Watchlist Scan runs daily at 17:30; Earnings Risk Brief runs daily for portfolio companies with earnings in T+1 day.

### AI Recommendation Quality and Transparency
15. Every AI recommendation must carry confidence level, historical sample size, and cited sources — displayed inline, not in fine print.
16. When fewer than 5 historical analogies exist, a clear disclaimer must accompany the recommendation.
17. Every recommendation, score, and map color must have a traceable "why" explanation reachable in one click.
18. AI confidence + sample_size must always be visible; ex-post accuracy is tracked.
19. Confidence thresholds: auto_send >= 0.7; HIL queue 0.4–0.7; do_not_send < 0.4 (configurable per workflow).
20. Workflow confidence equals the minimum confidence across all critical AgentNodes in that workflow.
21. On low confidence (0.4–0.7), the system must route to the HIL review queue and block auto-send.
22. On very low confidence (< 0.4), output must be blocked and not sent.

### Agent Architecture
23. The system operates in exactly two modes: Reactive Pipeline (Mode A) and Deliberative Workflows (Mode B).
24. Every agent node must use only the tools explicitly listed in its YAML definition — no more, no less.
25. Agents are defined by named roles with: role_id, persona, system_prompt_file, model config, tools list, limits (max_input_tokens, max_iterations, timeout_seconds, cost_ceiling_usd), confidence_threshold, and output_schema.
26. Agent definition files reside at `agents/{role_id}.yaml`.
27. Nine named-role agents are defined with heterogeneous model assignments.
28. Q&A Analyst supports max_iterations = 10; all other agents: 3–5.
29. The evaluate_quality node is always second-to-last in every workflow; Narrative Writer is always the last agent node.
30. Historical Context Agent is reused across all five workflows.
31. All tool calls must return bounded outputs (max 50 rows) and use the standard error contract (ToolNotApplicable / InsufficientData / RateLimited).
32. Tool outputs must be cached per workflow run.

### Prompt Management
33. Prompts are stored in the database (versioned via Langfuse), always using the latest production version.
34. Prompt source of truth is git (`prompts/*.md` with frontmatter); runtime access is via Langfuse.
35. Prompt promotion workflow: Draft → PR (with Tier 2 golden dataset run) → Review → Merge → Staging label → Canary traffic → Tier 1+3 monitoring → Promote to production.
36. Rollback of a prompt must take effect within seconds via `stokai prompts rollback --agent <role> --to-version <sha>`.
37. Tier 2 golden dataset regression hard gate: cannot promote a prompt if it performs worse than production by > 5% on any metric.

### Memory System
38. Every AI reasoning step and decision must be stored in the database for audit.
39. Semantic facts require evidence_count >= 3 before commit to semantic memory.
40. Semantic facts decay if unconfirmed for 6 months.
41. Every HIL action (Approve / Edit & Approve / Reject / Reject with feedback) writes to user feedback memory (Layer 4).
42. A weekly offline job aggregates feedback patterns, generates proposed prompt/threshold adjustments, and requires human approval before changes are applied.
43. Memory hygiene: quarterly review, decay functions, and explicit retraction applied to all memory layers.
44. Procedural memory v2 automation: a weekly job mines episodic memory for patterns.

### Data and Caching
45. Every fetch is saved locally with timestamp and TTL; external APIs are the last resort (cache-or-fetch rule: Redis → PostgreSQL → external API only on cache miss).
46. Historical data (past prices, embeddings) is fetched once and never re-fetched (immutable past; infinite TTL).
47. Computed scores are invalidated event-driven, not on a fixed schedule.
48. Price freshness default is 15-minute delay; real-time switch is a parameter change, not a code change.
49. All data sources are configurable through the admin panel; no hardcoding of provider selections.
50. Adding a new market must require only a MARKET_REGISTRY entry and (optionally) a new provider adapter.
51. Twitter/X free API is used for MVP; $100/month paid tier is optional and user-decision-dependent.
52. GDELT commercial license must be verified before launch; ACLED is the designated backup.
53. Historical data (past prices, embeddings) is fetched once and never re-fetched (immutable past).

### Alerting and Anti-Fatigue
54. Anti-fatigue controls (daily push limit, quiet hours, per-ticker threshold, deduplication) govern all alert dispatch.
55. Per-user/day cost limits are enforced: daily_budget_usd, daily_alert_threshold_pct, daily_hard_stop_pct.

### Multi-tenancy and Security
56. Every user data table carries tenant_id from day one, enforcing row-level isolation.
57. Even in single-user MVP, login is required; the user table must have a role field (admin/operator vs end-user) from day 1.
58. Admin panel access is gated by role (admin/operator vs end-user).
59. Credentials stored in secrets vault, never as plaintext; source_config holds vault references only.

### Evaluation and Calibration
60. Every production workflow output must be evaluated by Tier 1 LLM-as-judge before delivery.
61. Tier 3 ex-post calibration must run daily and be reviewed weekly, tracking recommendations vs market outcomes at T+1d and T+1w.

### UI and User Experience
62. The application must open directly to the map; no landing dashboard may bury the map one click deep.
63. UI depth follows progressive disclosure: pulse → popup (3-second read) → side panel (30-second read) → full analysis (deep dive); the user controls depth.
64. The interface must be calm by default and only escalate visual prominence for high-intensity, high-relevance events (anti-fatigue visual rule).
65. The decision interface (map + panels) is desktop-first; alerts and brief-reading are mobile-first.
66. At world zoom (z0–z2) events must be clustered; at z7+ every event renders as an individual pulse with full granularity.
67. A single intensity-5 event must punch through as an individual pulse even at low zoom — it must never hide inside a cluster.
68. New-user first-run must offer preset scoring profiles and guided portfolio setup to prevent empty-map bounce.
69. Empty/quiet states must display meaningful human-readable messages, not a blank or error state.
70. The admin panel must allow enable/disable of any data source without a code deploy; disabling reroutes to the configured fallback.
71. Feature flags (real-time mode, specific workflows, social sources) must be toggleable per environment from the admin panel.

### Scoring
72. Scoring profiles (Value Investor, Growth Hunter, Macro Aware) switch the entire market rating and map coloring.
73. Indicator Builder accepts DSL formulas; the Scoring Engine normalizes against benchmark and applies a geo modifier.
74. Every Indicator Builder save must create a new version; diff and rollback between versions must be supported.

## Contradictions Detected

| ID | Statement A | Source A | Statement B | Source B | Type |
|----|-------------|----------|-------------|----------|------|
| C-001 | Morning Brief runs daily at 05:30 | architectural_considerations.md §Business Rules item 20 | Morning Brief is delivered at 06:00 daily via HTML email | system_description.md §Business Rules item 19 | Hard conflict |
| C-002 | Total projected cost ~$430–520/month (AI + data + infra) | architectural_considerations.md §Non-Functional Signals | Total MVP infrastructure cost target ~$268/month (AI $30–50 + Azure $30–40) | system_description.md §Non-Functional Signals | Hard conflict |
| C-003 | LLM roles: Claude Haiku 4.5 for classification/extraction, Sonnet 4.6 for alert/filter, Opus 4.7 for reasoning agents | architectural_considerations.md §Integration Points | LLM roles: Azure OpenAI GPT-4o-mini for high-volume classification + embeddings (VNet-isolated); Claude Opus for complex reasoning | system_description.md §Integration Points | Soft conflict |
| C-004 | MARKET_REGISTRY is a code-level dict[str, MarketConfig] — the single extension point for new markets | system_description.md §Architecture Signals | MARKET_REGISTRY must migrate from code constants to database-backed service (market_source_binding table); market-to-source binding must be DB-backed and admin-editable | ui_design.md §Architecture Signals | Soft conflict |
| C-005 | Reactive Pipeline described as "12-step fixed sequence" in body text (steps 1–12 enumerated) | architectural_considerations.md §Business Rules item 18 | Decision Summary refers to a "13-step fixed sequence" (ambiguity noted within same document — possible off-by-one in step counting) | architectural_considerations.md §Ambiguities Detected | Scope overlap |
| C-006 | Twitter/X Filtered Stream used as primary real-time social signal source for Mode A trigger | architectural_considerations.md §Integration Points | Twitter/X must be off by default in the admin panel; social source activation requires explicit admin toggle | ui_design.md §Business Rules item 44 | Scope overlap |

## Cross-Domain Dependencies

- Depends on: (none identified — all three source documents are root-domain files; this synthesis is self-contained)
- Referenced by: All downstream domain syntheses and the master synthesis will depend on the root domain for core system rules, agent architecture, and integration point definitions.
- The root domain defines the canonical entity models (WorkflowState, geo_event, company, market, etc.) and integration contracts (provider abstractions, LLM model assignments) that all other domains must treat as fixed constraints.
- Prompt governance pipeline (git + Langfuse) is defined here and consumed by any future agentic or evaluation domain.

## NFR Candidates

- Latency / Performance: Event-to-alert ≤90 s end-to-end (Mode A); Tweet-to-alert ≤30 s (TIER1); Score-change alert ≤5 min; SEC filing alert ≤20 min (seen in 2 docs)
- Latency / Performance: Reactive Pipeline LLM budget ~60 s; latency hard limits per workflow type (Morning Brief 10 min, On-Demand 6 min, Watchlist 8 min, Earnings Brief 10 min, Event Deep-Dive 15 min) (seen in 1 doc)
- Cost / Efficiency: $0.05 ceiling per Mode A event; $0.50–$2.00 ceiling per Mode B report (seen in 1 doc)
- Cost / Budget: Per-user daily budget enforcement with hard-stop threshold (seen in 1 doc)
- Cost / Operability: MVP total infrastructure cost target (conflicting figures — see C-002; resolution needed before NFR finalisation) (seen in 2 docs)
- Performance / Predictability: All tool outputs bounded to max 50 rows; per-agent limits (max_input_tokens, max_iterations, timeout_seconds, cost_ceiling_usd) (seen in 1 doc)
- Reliability / Resilience: LangGraph checkpointing to PostgreSQL for failure recovery, HIL pause/resume, and replay (seen in 1 doc)
- Reliability: Rate limiting on free APIs mitigated by aggressive cache + nightly batch + Redis TTL per endpoint (seen in 1 doc)
- Observability: Langfuse self-hosted with hierarchical per-run traces; all AI reasoning stored to DB for audit (seen in 1 doc)
- Operational Agility / Availability: Prompt rollback effective within seconds (seen in 1 doc)
- Quality / Regression Safety: Golden dataset regression gate — > 5% degradation blocks promotion (seen in 1 doc)
- Accuracy / Continuous Improvement: Tier 3 ex-post calibration daily run with weekly review (seen in 1 doc)
- Data Freshness / Integrity: Semantic fact decay after 6 months unconfirmed (seen in 1 doc)
- Maintainability / Data Governance: Memory hygiene with quarterly review and decay functions (seen in 1 doc)
- Compliance / Auditability: Audit log of every AI reasoning step stored in DB; ex-post accuracy tracked; AI override feedback loop (seen in 2 docs)
- Compliance / Legal: System operates on derived data; clear disclaimers on low-sample recommendations (seen in 1 doc)
- Cost / Self-hostability: Self-hosted Langfuse; no hard Azure lock-in; `docker compose up` parity (seen in 2 docs)
- Flexibility / Configurability: Configurable model per agent role; confidence thresholds configurable per workflow; feature flags per environment (seen in 2 docs)
- Scalability / Cost: Local-first cache ensures data cost grows sublinearly with user count; viewing a chart 100× incurs 0 additional API calls (seen in 1 doc)
- Security / Multitenancy: Row-level tenant isolation via tenant_id; credentials in vault, never plaintext; role-based access from day 1 (seen in 2 docs)
- Portability / Operability: No hard Azure lock-in; Docker + Compose / K8s containerisation across all components; 12-factor app compliance (seen in 1 doc)
- Performance / Scalability: pgvector HNSW index for semantic search; TimescaleDB hypertables for OHLCV (seen in 1 doc)
- Accessibility: Colorblind-safe palette mandated for map pulse categories (seen in 1 doc)
- Responsive Design: Mobile-first for alerts and brief-reading; desktop-first for map decision interface (seen in 1 doc)
- UX Responsiveness: 3-second read popup constraint; 30-second read side panel constraint (seen in 1 doc)
- Data Retention / Time-series Storage: Score history required for Historical mode time-machine isolation (seen in 1 doc)
- Operational Configurability: Admin enable/disable of data source takes effect at runtime without code deploy (seen in 1 doc)
- Cost Observability: Admin cost monitor with threshold alerts; per-source/model/workflow cost breakdown (seen in 1 doc)

## Ambiguities Detected

- Morning Brief delivery time is stated as both 05:30 (architectural_considerations.md) and 06:00 (system_description.md) — requires authoritative decision before scheduling implementation. [See C-001]
- Total MVP cost figures conflict: $430–520/month vs $268/month — itemised breakdown does not reconcile with either figure; a detailed cost model is required. [See C-002]
- LLM provider assignment for high-volume classification conflicts between the two architecture documents: Anthropic Haiku 4.5 vs Azure OpenAI GPT-4o-mini. The contradiction decision log (memory: C-001–C-006, "multi-provider LLM") indicates this was addressed externally but the documents do not reflect the resolved state. [See C-003]
- MARKET_REGISTRY persistence: code dict (system_description.md) vs DB-backed service (ui_design.md) — architectural decision on migration scope and timing is required. [See C-004]
- Reactive Pipeline step count: body text says 12 steps; Decision Summary cited 13 — one-off counting discrepancy must be resolved to avoid implementation error.
- Twitter/X free API: memory decisions reference "free Twitter/X" but the Filtered Stream API has no documented free tier at the volume required; verification of the exact endpoint and access mechanism is outstanding.
- GDELT commercial license status for MVP use is unverified; ACLED is designated fallback but its coverage scope is not specified.
- Canary traffic percentage and duration for prompt promotion are not defined in any document.
- HIL "timing windows per workflow type" are referenced in architectural_considerations.md but not specified for any workflow.
- Admin panel implementation (same React app under /admin route vs separate bundle): decision is deferred; criterion for choosing is absent.
- "~100–200 tracked companies" is a soft figure; the hard upper limit and criteria for promoting on-demand companies to tracked status are not defined.
- Action signal CONTRARIAN: conditions under which CONTRARIAN is chosen vs HEDGE are not defined.
- Score history retention period, granularity, and storage strategy for Historical mode time-machine are not specified.
- Procedural memory v1 initial patterns: who authors them, what completeness criteria exist before Phase 4 go-live, are unspecified.
- User feedback "immediate effect (rejected = not sent)": whether this applies only to the current run or also retroactively removes already-delivered content is unclear.
- "OAuth2 production" auth is mentioned but MVP username/password boundaries vs OAuth2 scope are undefined.
- ui_design.md is explicitly self-flagged as a proposal that "should be rethought to fulfill all functional requirements from system_description.md" — scope finality of the UI specification is unresolved.
- Model IDs "Claude Opus 4.7" and "Claude Sonnet 4.6" are forward-dated (document version May 2026); it is unclear whether these are placeholder names or confirmed model IDs.

## Architecture-Relevant Files

- architectural_considerations.md (explicit — doc_type: architecture)
- system_description.md (explicit — doc_type: architecture)
- ui_design.md (auto — heuristic: contains significant architectural signals including frontend stack mandate, DB migration requirement, and adapter pattern specification)
