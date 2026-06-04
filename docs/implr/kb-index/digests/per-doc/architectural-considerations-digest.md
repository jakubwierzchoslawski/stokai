---
source_file: docs/kb/architectural_considerations.md
checksum: eb14e952c74f04a1c44f12aee13ecc55
digested_at: 2026-06-02T00:00:00Z
domain: root
doc_type: architecture
arch_relevant: true
---

# Digest: architectural_considerations.md

## Business Rules

1. The system operates in exactly two modes: Reactive Pipeline (Mode A) and Deliberative Workflows (Mode B); no hybrid or fallback mode is defined.
2. Mode A is triggered by external events (Tweet, GDELT poll, SEC EDGAR filing, price anomaly) and must complete within 90 seconds at a cost ceiling of $0.05 per event.
3. Mode B is triggered by cron schedule, user request, Mode A event, or watchlist alarm, with a cost ceiling of $0.50–$2.00 per report and a latency target of 2–5 minutes.
4. Every agent node must use only the tools explicitly listed in its YAML definition — no more, no less.
5. Agents are defined by named roles with: role_id, persona, system_prompt_file, model config, tools list, limits (max_input_tokens, max_iterations, timeout_seconds, cost_ceiling_usd), confidence_threshold, and output_schema.
6. Agent definition files reside at `agents/{role_id}.yaml`.
7. Prompts are stored in the database (versioned via Langfuse), always using the latest production version.
8. Prompt source of truth is git (`prompts/*.md` with frontmatter); runtime access is via Langfuse.
9. Prompt promotion workflow is: Draft → PR (with Tier 2 golden dataset run) → Review → Merge → Staging label → Canary traffic → Tier 1+3 monitoring → Promote to production.
10. Rollback of a prompt must take effect within seconds via `stokai prompts rollback --agent <role> --to-version <sha>`.
11. Every AI reasoning step and decision must be stored in the database for audit. User overrides or adjustments must trigger corresponding changes to prompts or system configuration.
12. Semantic facts require evidence_count >= 3 before commit to semantic memory.
13. Semantic facts decay if unconfirmed for 6 months.
14. Workflow confidence equals the minimum confidence across all critical AgentNodes in that workflow.
15. Confidence thresholds: auto_send >= 0.7; hil_queue 0.4–0.7; do_not_send < 0.4 (configurable per workflow).
16. Every HIL action (Approve / Edit & Approve / Reject / Reject with feedback) writes to user feedback memory (Layer 4).
17. A weekly offline job aggregates feedback patterns, generates proposed prompt/threshold adjustments, and requires human approval before changes are applied.
18. The Reactive Pipeline is a 12-step fixed sequence with no tools, no loops, no decision branches.
19. Deep-dive Mode B job is enqueued if event intensity >= 4 or portfolio match is detected in step 12 of the pipeline.
20. Morning Brief runs daily at 05:30; Watchlist Scan runs daily at 17:30; Earnings Risk Brief runs daily for portfolio companies with earnings in T+1 day.
21. The evaluate_quality node is always second-to-last in every workflow; Narrative Writer is always the last agent node.
22. Historical Context Agent is reused across all five workflows.
23. Tier 2 golden dataset regression hard gate: cannot promote a prompt if it performs worse than production by >5% on any metric.
24. Per-user/day cost limits are enforced: daily_budget_usd, daily_alert_threshold_pct, daily_hard_stop_pct.
25. No autonomous trading, no open-ended exploration, no multi-agent debate, no prompt injection surface are permitted.

## System Behaviours Required

- On external event arrival, the system must: persist raw event, classify (Haiku 4.5, <5s), extract tickers (Haiku 4.5, <3s), compute exposure map, persist event record, embed event (OpenAI, <2s), find historical analogies (pgvector), generate alert text (Sonnet 4.6, ~80 words, <8s), evaluate alert rules, dispatch or log silent, enqueue deep-dive if applicable.
- Reactive Pipeline must complete within 90 seconds end-to-end from event arrival to user alert.
- Mode B workflows execute as LangGraph StateGraph with DeterministicNode or AgentNode per step.
- Workflow state (WorkflowState Pydantic model) must be passed between all nodes and contain: workflow_id, tenant_id, user_id, inputs, portfolio_state, events, relevant_events, score_changes, anomalies, analogies, recommendations, report, confidence_scores, requires_hil, cost_usd, tokens_consumed.
- Independent agent invocations within a workflow must execute in parallel via asyncio.gather.
- Every node must have enforced: timeout_seconds, max_retries, cost_ceiling_usd.
- LangGraph workflow state must be checkpointed to PostgreSQL for failure recovery, HIL pause/resume, and replay.
- On low-confidence output (0.4–0.7), the system must route to the HIL review queue and block auto-send.
- On very low confidence (<0.4), output must be blocked and not sent.
- HIL Review Queue UI must present pending items sorted by scheduled send time with actions: Approve, Edit & Approve, Reject, Reject with feedback.
- Every production workflow output must be evaluated by Tier 1 LLM-as-judge before delivery.
- Tier 3 ex-post calibration must run daily and be reviewed weekly, tracking recommendations vs market outcomes at T+1d and T+1w.
- Q&A Analyst supports max_iterations = 10 (all other agents: 3–5).
- All tool calls must return bounded outputs (max 50 rows) and use the standard error contract (ToolNotApplicable / InsufficientData / RateLimited).
- Tool outputs must be cached per workflow run.
- Procedural memory v2 automation: a weekly job mines episodic memory for patterns.
- Memory hygiene: quarterly review, decay functions, explicit retraction applied to memory layers.
- Morning Brief budget: 4–5 min, $1.50–$2.00. On-Demand budget: 3–4 min, $1.00–$1.50. Watchlist Scan: 3 min, $1.00. Earnings Brief: 4 min, $1.50. Event Deep-Dive: 5–7 min, $2.00.
- Reactive Pipeline LLM budget: ~60s. Latency hard limits: Morning Brief 10 min, On-Demand 6 min, Watchlist 8 min, Earnings Brief 10 min, Event Deep-Dive 15 min.

## Data Entities

- WorkflowState: workflow_id, tenant_id, user_id, inputs, portfolio_state, events, relevant_events, score_changes, anomalies, analogies, recommendations, report, confidence_scores, requires_hil, cost_usd, tokens_consumed
- workflow_run: (episodic memory table) — full record of each workflow run
- agent_invocation: (episodic memory table) — record per agent invocation
- tool_call: (episodic memory table) — record per tool call
- recommendation_outcome: (episodic memory table) — outcome tracking per recommendation
- semantic_fact: entity facts with pgvector embeddings, evidence_count, last_confirmed timestamp
- procedural_pattern: reasoning patterns with hand-authored (v1) and mined (v2) entries
- user_feedback: explicit user signals (approve/reject/edit/thumbs) per output
- alert: alert row produced by Reactive Pipeline
- geo_event: geo event row produced by Reactive Pipeline
- event_embedding: pgvector embedding stored per event
- AgentDefinition (YAML): role_id, persona, system_prompt_file, model (provider, model_id, temperature, max_tokens), tools, limits, confidence_threshold, output_schema
- LangfuseTrace: workflow_id, tenant_id, agent_role_id, prompt_version, model_used, confidence, cost_usd, tokens, latency, tools_called

## Integration Points

- X (Twitter) Filtered Stream: real-time tweet event source for Mode A trigger
- GDELT: polled event source for Mode A trigger
- SEC EDGAR: filing source for Mode A trigger
- Price data provider: price anomaly source for Mode A trigger
- OpenAI text-embedding API: event embedding in Reactive Pipeline step 7
- Claude Haiku 4.5 (Anthropic): classify_event (<5s) and extract_tickers (<3s) in Reactive Pipeline
- Claude Sonnet 4.6 (Anthropic): generate_alert_text in Reactive Pipeline; Relevance Analyst, Anomaly Detector, Exposure Analyst agents
- Claude Opus 4.7 (Anthropic): Historical Context Agent, Recommendation Synthesizer, Earnings Context Agent, Event Deep-Dive Agent, Narrative Writer, Q&A Analyst
- Langfuse self-hosted: observability, prompt management, evaluation dataset management, trace storage (backed by PostgreSQL + Clickhouse)
- Clickhouse: Langfuse analytics backend
- PostgreSQL + TimescaleDB + pgvector: shared database for both modes — events, memory, workflow state, checkpointing, episodic memory tables
- Celery workers: LangGraph workflow runtime execution
- Frontend HIL Review UI: web UI for human-in-the-loop queue review and approval
- Git: prompt source versioning (prompts/*.md), prompt SHA used as Langfuse version label
- Email/notification system: delivery of reports and alerts to users

## Non-Functional Signals

- <90s end-to-end latency for Reactive Pipeline → Latency / Performance NFR candidate
- $0.05 cost ceiling per Mode A event → Cost / Efficiency NFR candidate
- $0.50–$2.00 cost ceiling per Mode B report → Cost / Efficiency NFR candidate
- ~$251/month projected AI cost; ~$430–520/month total (AI + data + infra) → Cost / Budget NFR candidate
- Per-user daily budget enforcement with hard-stop threshold → Cost / Resource Governance NFR candidate
- All tool outputs bounded to max 50 rows → Performance / Predictability NFR candidate
- Per-agent limits: max_input_tokens, max_output_tokens, max_iterations, timeout_seconds, cost_ceiling_usd → Reliability / Bounded Execution NFR candidate
- LangGraph checkpointing to PostgreSQL for failure recovery and replay → Reliability / Resilience NFR candidate
- Langfuse self-hosted from day 1 with hierarchical per-run traces → Observability NFR candidate
- Prompt rollback effective within seconds → Operational Agility / Availability NFR candidate
- Golden dataset regression gate (>5% degradation blocks promotion) → Quality / Regression Safety NFR candidate
- Tier 3 calibration daily run with weekly review → Accuracy / Continuous Improvement NFR candidate
- Semantic fact decay after 6 months unconfirmed → Data Freshness / Integrity NFR candidate
- Memory hygiene with quarterly review and decay functions → Maintainability / Data Governance NFR candidate
- Audit log of every AI reasoning and decision stored in DB → Compliance / Auditability NFR candidate
- Self-hosted Langfuse to avoid enterprise licensing costs → Cost / Self-hostability NFR candidate
- Configurable model per agent role → Flexibility / Configurability NFR candidate
- Confidence thresholds configurable per workflow → Configurability NFR candidate

## Ambiguities Detected

- The Reactive Pipeline is described as 12-step in Section 12 but the Decision Summary says it is a "13-step fixed sequence" — the actual numbered list has 12 items (steps 1–12); it is unclear whether step counting includes the trigger event arrival or not.
- Model IDs "Claude Opus 4.7" and "Claude Sonnet 4.6" are referenced but these are forward-dated versions (document version May 2026); it is unclear whether these are placeholder names or confirmed model IDs.
- "Multi-provider LLM" is referenced in memory as a contradiction decision (C-001–C-006), but this document references only Anthropic Claude and OpenAI embedding — it is unclear how provider switching or fallback is implemented.
- The $251/month AI cost projection vs $430–520/month total is stated but no detailed cost breakdown per workflow or per provider is provided; data and infra cost sources are unspecified.
- Procedural memory v1 is "mostly read-only (hand-authored patterns)" — it is unclear what the initial patterns are, who authors them, or how completeness is determined before Phase 4 go-live.
- User feedback "immediate effect (rejected = not sent)" — it is unclear whether this applies only to the current run or also retroactively removes already-delivered content.
- The HIL "timing windows per workflow type" are referenced but not specified for any workflow.
- Canary traffic percentage and duration for prompt promotion are not defined.
- Free Twitter/X access model (from memory decisions) conflicts with "X Filtered Stream" which typically requires elevated API access — the mechanism for free access is unspecified.
- The Q&A Analyst's max_iterations = 10 is higher than other agents (3–5); no rationale or safety bound for runaway Q&A sessions is stated beyond the per-agent cost_ceiling_usd.
- "Agents access only tools listed in their YAML definition — no more, no less" — enforcement mechanism (runtime guard, test, or convention) is not specified.

## Architecture Signals

- Hybrid deterministic + agentic architecture: Reactive Pipeline (Mode A) is fully deterministic with fixed LLM call chain; Deliberative Workflows (Mode B) use LangGraph graph-based orchestration with AgentNodes.
- LangGraph (Python, graph-based) chosen as workflow orchestration framework; Celery workers host the runtime.
- PostgreSQL + TimescaleDB + pgvector is the single shared database across both modes — no separate event store, vector store, or cache layer is defined.
- pgvector used for semantic similarity search (find_similar_events top-K) within the same PostgreSQL instance.
- Langfuse self-hosted (PostgreSQL + Clickhouse) chosen over LangSmith for cost and self-host reasons; Clickhouse is a required additional infrastructure component.
- Agent definitions are externalised to YAML files (agents/{role_id}.yaml) — agent behaviour is data-driven and configurable without code changes.
- Prompts are dual-homed: git is source of truth, Langfuse is runtime access; this creates a two-system dependency for prompt delivery.
- Four-layer memory architecture (episodic, semantic, procedural, user feedback) implemented from day 1 in MVP — no incremental rollout of memory layers.
- WorkflowState as a single shared Pydantic model passed between all LangGraph nodes — centralised state, no message-passing between agents.
- Confidence score drives automated routing: high → auto-send, medium → HIL queue, low → block. This is the primary quality gate.
- HIL Review Queue is a required UI component; frontend must implement this for the system to be production-ready.
- Nine named-role agents with heterogeneous model assignments (Haiku for classification speed, Sonnet for filtering, Opus for reasoning-heavy tasks).
- Tool Library is a scoped, bounded abstraction layer between agents and data — agents never access DB or APIs directly.
- Episodic memory is append-only with indefinite retention — no archival or deletion strategy defined.
- Three-tier evaluation framework (online LLM-judge, golden dataset regression, ex-post calibration) operates continuously in production.
- Parallelism via asyncio.gather for independent agent invocations — async-first execution model within workflows.
- All five workflows share the same evaluate_quality → Narrative Writer tail pattern — this is a mandated cross-workflow architectural convention.
- Phase 4 = agentic layer build (Tool Library, first 3 agents, Morning Brief, Langfuse + Tier 3 from day 1); Phase 5 = all 9 agents, all 5 workflows, semantic/procedural memory, HIL UI — two-phase rollout with Langfuse observability mandatory from Phase 4.
- New infrastructure components added to master architecture: Langfuse service, Clickhouse, LangGraph workflow runtime in Celery, HIL Review UI, new DB tables (workflow_run, agent_invocation, tool_call, semantic_fact, procedural_pattern, user_feedback), new API endpoints (HIL queue, on-demand trigger, Q&A interface).
