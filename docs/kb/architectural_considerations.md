# StokAI — Agentic Architecture

> **Companion document to STOCKIQ.md**
> Where the Master Architecture answers *what data and structure*, this document answers *how intelligence flows through it*.
> Version 1.0 — May 2026 · Status: **Ready for implementation**

---

## Decision Summary

| Decision | Value |
|---|---|
| Operational model | Two modes: Reactive Pipeline + Deliberative Workflows |
| Orchestration framework | LangGraph (Python, graph-based) |
| Agent design | Named roles with personas, scoped business-function tools |
| Memory subsystem | All four layers from day 1 (episodic, semantic, procedural, user feedback) |
| Quality control | Web UI review queue for low-confidence reports (HIL) |
| Model assignment | Configurable per agent role |
| Observability | Langfuse self-hosted from day 1 |
| Evaluation | Three tiers from MVP (online LLM-judge, golden dataset, ex-post calibration) |
| Prompt versioning | Hybrid — source in git, deployed and tracked via Langfuse |
| Workflows fully documented | 5 (Morning Brief, On-Demand Analysis, Watchlist Scan, Earnings Risk Brief, Event Deep-Dive) |
| Audit | Each AI reasoning and decision has to be stored in DB for further. In case of user override or adjust the ai system has to be adjusted as well like prompts etc|

---

## Table of Contents

**Foundations**
- [Section 00 — Executive Summary](#section-00--executive-summary)
- [Section 01 — Two Modes: Reactive Pipeline vs Deliberative Workflows](#section-01--two-modes-reactive-pipeline-vs-deliberative-workflows)
- [Section 02 — Workflow Anatomy](#section-02--workflow-anatomy)

**Agent Layer**
- [Section 03 — Agent Registry](#section-03--agent-registry)
- [Section 04 — Tool Library](#section-04--tool-library)
- [Section 05 — Memory Subsystem](#section-05--memory-subsystem)
- [Section 06 — Quality Control & Human-in-the-Loop](#section-06--quality-control--human-in-the-loop)

**Implementation**
- [Section 07 — LangGraph Implementation](#section-07--langgraph-implementation)
- [Section 08 — Observability Stack](#section-08--observability-stack)
- [Section 09 — Evaluation Framework](#section-09--evaluation-framework)
- [Section 10 — Prompt Management](#section-10--prompt-management)

**Workflows**
- [Section 11 — The Five Core Workflows](#section-11--the-five-core-workflows)
- [Section 12 — The Reactive Pipeline](#section-12--the-reactive-pipeline)

**Operations**
- [Section 13 — Cost & Latency Budgets](#section-13--cost--latency-budgets)
- [Section 14 — Integration with Master Architecture](#section-14--integration-with-master-architecture)

---

## Section 00 — Executive Summary

*What the agentic layer is, what it isn't, and why*

The StokAI agentic layer is not "agents all the way down." It is a deliberate hybrid: a deterministic reactive pipeline for real-time event handling (where speed and predictability win), and a graph-orchestrated agentic system for deliberative analysis (where reasoning quality wins).

### The core insight

Real-time alerts and deep analytical reports have fundamentally different requirements. An alert needs to fire in 90 seconds, every time, with predictable cost. A report can take 5 minutes and cost $2 if the analysis is rigorous. Conflating these into one architecture compromises both.

So we split them:

- **Reactive Pipeline (Mode A)** — fixed chain of LLM calls and deterministic operations. No agents, no tool loops, no decision branches. Triggered by external events. Produces alerts and notifications. Target: 90 seconds, $0.05 per event.

- **Deliberative Workflows (Mode B)** — LangGraph workflows where each node is either deterministic code or a named-role agent with scoped tools. Triggered by schedule or user action. Produces reports and analyses. Target: 2-5 minutes, $0.50-$2.00 per report.

Both modes write to the same memory subsystem, so the system learns continuously across both. Both modes are fully observable via Langfuse. Both modes are subject to the same evaluation framework.

### What makes this "agentic"

Three things distinguish this from a glorified prompt chain:

1. **Named role agents.** Each agent (Relevance Analyst, Anomaly Detector, Recommendation Synthesizer, etc.) is a first-class citizen with its own persona, system prompt, scoped toolset, and configurable model. Not lambdas. Not nodes. Analysts.

2. **Long-term memory across four layers.** Episodic (every past run), semantic (learned facts about entities), procedural (what reasoning approaches work), and user feedback (what you marked as good or bad). The system gets smarter over time.

3. **Tool-mediated data access.** Agents never touch raw infrastructure. They call pre-built business functions (`get_portfolio_state`, `find_similar_events`, `compute_exposure`) that present a clean, typed view of the world. This is safety, consistency, and observability in one design.

### What this layer does NOT do

To be clear about scope:

- **No autonomous trading.** Agents never execute transactions. They produce recommendations and frameworks. Humans decide.
- **No open-ended exploration.** Agents do not browse the web, read arbitrary documents, or "look around." They use the tools they have. If a tool is missing, the agent says so — it does not improvise.
- **No multi-agent debate.** Agents do not converse with each other. The graph structure determines the flow. Adversarial review (Skeptic agent) is a future option but not in v1.
- **No prompt injection surface.** Agents do not consume untrusted user content as instructions. User questions are data, not directives.

---

## Section 01 — Two Modes: Reactive Pipeline vs Deliberative Workflows

*The fundamental architectural split*

### Mode A — Reactive Pipeline (deterministic, real-time)

**Purpose:** Convert external events into alerts and stored analyses, fast.

**Triggers:** Tweet from X Filtered Stream · GDELT event poll · SEC EDGAR filing · Price anomaly

**Structure:** A fixed sequence of nodes. Each node is either deterministic code or a single scoped LLM call (no tools, no loop, no decision branch). The output of step N is the input of step N+1.

**Why not agents here:** Three reasons. (1) Latency budget is 90 seconds — there's no time for an agent to "think about what to do." (2) The work itself is well-defined: classify, extract, match, summarize, dispatch. No analytical judgment is required at the structural level. (3) Cost predictability — one LLM call per step, fixed token counts, no loops.

**What it produces:**
- An `alert` row (if rules match) → push/email to user
- A `geo_event` row in the database
- An `event_embedding` row in pgvector
- An entry in episodic memory ("event X classified at T with confidence Y")
- An enqueued job for the Event Deep-Dive workflow (Mode B), to run asynchronously

**Key property:** The Reactive Pipeline is a *publisher* into the Deliberative system. Every event that matters gets the fast alert path AND triggers a slow deep-dive. The user gets both: 30-second alert, 5-minute follow-up.

### Mode B — Deliberative Workflows (agentic, scheduled/on-demand)

**Purpose:** Produce reports, analyses, and synthesized intelligence with deep reasoning.

**Triggers:** Cron schedule (Morning Brief at 06:00) · User request (analyze this company) · Event from Mode A (deep-dive on TIER1 tweet) · Watchlist alarm (significant score change)

**Structure:** A LangGraph workflow — a directed graph where nodes are either `DeterministicNode` (plain code, no LLM) or `AgentNode` (named-role agent with tools). State flows through the graph; agents read shared state and produce structured outputs.

**Why agents here:** Analytical judgment is the whole point. "Which of these 47 overnight events actually matter for THIS user's portfolio?" requires reasoning about relevance, exposure, and user context. That's an analyst's job, not a function.

**What it produces:**
- A `report` artifact (Morning Brief, Analysis Document, etc.)
- Updates to long-term memory (semantic, procedural, episodic)
- Recommendations with confidence scores
- HIL queue entries for low-confidence outputs
- Email/UI delivery once approved (or auto-sent if confidence is high)

### Comparison table

| Aspect | Mode A — Reactive | Mode B — Deliberative |
|---|---|---|
| Trigger | External event | Schedule / user / Mode A handoff |
| Latency target | < 90 seconds | 2-5 minutes |
| Cost per run | ~$0.05 | $0.50-$2.00 |
| Decision branching | None — fixed pipeline | Yes — graph topology |
| Tool use | No | Yes — scoped business functions |
| Loops / retries | No | Yes — bounded by node config |
| Output | Alert, classified event | Report, analysis, recommendations |
| Quality control | Confidence threshold on classifier | HIL queue for low-confidence outputs |
| Examples | Tweet alert, breaking geo alert | Morning Brief, Earnings Risk Brief |

### The shared substrate

Both modes share:
- The same database (PostgreSQL + TimescaleDB + pgvector)
- The same Memory Subsystem (all four layers)
- The same Tool Library (used by Mode B agents, called as plain functions by Mode A)
- The same observability stack (Langfuse traces both)
- The same evaluation framework (Tier 3 ex-post calibration runs on both)

This is critical: they are not two systems. They are two operating modes of one system, optimized for different latency profiles.

---

## Section 02 — Workflow Anatomy

*The DeterministicNode / AgentNode pattern*

A LangGraph workflow in StokAI is a directed graph where every node is one of two types. This binary distinction keeps the architecture simple and observable.

### DeterministicNode

A plain Python function. No LLM, no agent. Fetches data, transforms it, computes a metric, formats output, calls an external service.

```python
class DeterministicNode:
    name: str
    function: Callable[[WorkflowState], WorkflowState]
    timeout_seconds: int = 30
    retry_policy: RetryPolicy = NO_RETRY

    # Examples:
    # - fetch_portfolio_state()
    # - compute_overnight_price_changes()
    # - render_html_email_template()
    # - dispatch_via_sendgrid()
```

**Use a DeterministicNode when:**
- The work is mechanical (fetch, filter, transform, format)
- There is no analytical judgment involved
- The output is fully determined by inputs
- A function signature can express what the step does

### AgentNode

A named-role agent with persona, system prompt, scoped tools, and configurable model.

```python
class AgentNode:
    name: str                          # "Relevance Analyst"
    role_id: str                       # "relevance_analyst" (key in AgentRegistry)
    system_prompt_ref: str             # "prompts/relevance_analyst.md" + Langfuse version
    tools: list[ToolName]              # subset of Tool Library
    model: ModelConfig                 # which LLM, which params
    max_tokens_in: int                 # input budget
    max_tokens_out: int                # output budget
    max_iterations: int = 5            # tool-call loop bound
    confidence_threshold: float = 0.6  # below this → HIL queue
    output_schema: type[BaseModel]     # Pydantic model for structured output
```

**Use an AgentNode when:**
- Analytical judgment is required
- The work involves weighing, filtering, prioritizing, or synthesizing
- Multiple legitimate approaches exist and one must be chosen
- A human analyst would normally do this work

### The decision rule

When designing a workflow, every step gets this question: *would a human analyst need to think about this step, or just execute it?*

- "Fetch all events from the last 12 hours" → DeterministicNode
- "Which of these 47 events actually matter for the user's portfolio?" → AgentNode
- "Compute the percentile rank of each company in its sector" → DeterministicNode
- "Identify which score changes warrant attention and why" → AgentNode
- "Render the report as HTML" → DeterministicNode
- "Decide whether the overall recommendation is HOLD or REDUCE_RISK" → AgentNode

### The state object

LangGraph workflows pass a shared state object between nodes. For StokAI:

```python
class WorkflowState(BaseModel):
    workflow_id: UUID
    workflow_type: WorkflowType
    tenant_id: UUID
    user_id: UUID
    started_at: datetime

    # Input
    inputs: dict[str, Any]              # workflow-specific inputs

    # Accumulated artifacts
    portfolio_state: PortfolioState | None = None
    events: list[GeoEvent] = []
    relevant_events: list[RelevantEvent] = []
    score_changes: list[ScoreChange] = []
    anomalies: list[Anomaly] = []
    analogies: dict[UUID, list[Analogy]] = {}  # per event_id
    recommendations: list[Recommendation] = []
    report: Report | None = None

    # Quality control
    confidence_scores: dict[str, float] = {}   # per node
    requires_hil: bool = False
    hil_reason: str | None = None

    # Cost tracking
    cost_usd: float = 0.0
    tokens_consumed: dict[str, int] = {}       # per model
```

Every AgentNode reads from this state and writes back to it. Every DeterministicNode does the same. The state is the conversation between nodes.

---

## Section 03 — Agent Registry

*Every named role, defined declaratively*

The Agent Registry is the catalog of all named-role agents in the system. Each agent is defined once, used anywhere. Adding a new agent or modifying an existing one is a configuration change.

### Registry structure

```python
AGENT_REGISTRY: dict[str, AgentDefinition] = {
    "relevance_analyst": AgentDefinition(...),
    "anomaly_detector": AgentDefinition(...),
    "historical_context_agent": AgentDefinition(...),
    "recommendation_synthesizer": AgentDefinition(...),
    "exposure_analyst": AgentDefinition(...),
    "earnings_context_agent": AgentDefinition(...),
    "event_deep_dive_agent": AgentDefinition(...),
    "narrative_writer": AgentDefinition(...),
    "qa_analyst": AgentDefinition(...),
}
```

### Full agent specifications

#### Relevance Analyst

**Purpose:** Given a list of overnight events and the user's portfolio + watchlist, determine which events actually matter and why.

**Persona:** A senior buy-side analyst who has read 50,000 news items and knows which ones move markets and which are noise. Skeptical, calibrated, willing to say "nothing here is interesting today. Knows historical context and similar events impact on the market. It can cooperate with Historical Context Agent"

**Tools:** `get_portfolio_state`, `get_watchlist`, `get_company_exposures`, `query_recent_recommendations`

**Model (default):** Claude Sonnet 4.6 (cost-efficient for filtering work)

**Output schema:**
```python
class RelevanceAnalysis(BaseModel):
    relevant_events: list[RelevantEvent]
    excluded_events: list[ExcludedEvent]  # with reason
    overall_market_tone: str  # "risk_off" | "risk_on" | "mixed" | "quiet"
    confidence: float
    reasoning_summary: str
```

#### Anomaly Detector

**Purpose:** Identify score changes and metric movements that are unusual given historical patterns. Distinguish signal from drift.

**Persona:** A quantitative analyst with deep knowledge of base rates. Knows that a 2% move in a low-vol stock is more interesting than a 5% move in a high-vol one.

**Tools:** `get_score_history`, `compute_zscore`, `get_company_volatility`, `get_sector_baseline`

**Model (default):** Claude Sonnet 4.6

**Output schema:**
```python
class AnomalyReport(BaseModel):
    anomalies: list[Anomaly]
    confidence: float
    reasoning_summary: str
```

#### Historical Context Agent

**Purpose:** For each relevant event, find historical analogies and analyze how affected companies reacted then.

**Persona:** A market historian. Knows that "this time is different" is almost always wrong, but also knows when the analogy genuinely fails.

**Tools:** `find_similar_events` (pgvector semantic search), `get_price_reaction_to_event`, `compute_event_outcome_statistics`

**Model (default):** Claude Opus 4.7 (reasoning-heavy)

**Output schema:**
```python
class HistoricalContext(BaseModel):
    event_id: UUID
    analogies: list[Analogy]
    sample_size: int
    median_reaction_t1d: float
    median_reaction_t1w: float
    confidence_interval: tuple[float, float]
    confidence: float
    caveats: list[str]  # explicit warnings about analogy limits
```

#### Recommendation Synthesizer

**Purpose:** The capstone agent. Takes relevance analysis, anomalies, and historical context and produces actionable recommendations with confidence.

**Persona:** A portfolio manager writing the morning memo. Has to be decisive (HOLD/WATCH/BUY_OPP/REDUCE_RISK/HEDGE/CONTRARIAN) but transparent about uncertainty.

**Tools:** `get_portfolio_state`, `get_company_score_history`, `query_past_recommendations`, `compute_track_record`

**Model (default):** Claude Opus 4.7 (highest quality, this is the user-facing output)

**Output schema:**
```python
class RecommendationSet(BaseModel):
    per_company: list[CompanyRecommendation]
    overall_narrative: str
    key_risks: list[str]
    confidence: float
    requires_hil: bool  # set true if confidence < threshold
```

#### Exposure Analyst

**Purpose:** Given an event and a company, determine the type and magnitude of exposure (direct revenue, supply chain, sector, currency).

**Persona:** A research analyst who reads 10-Ks and knows how to trace a geopolitical event through a company's business model.

**Tools:** `get_company_fundamentals`, `get_geo_revenue_breakdown`, `get_supply_chain_dependencies`, `get_sector_correlations`

**Model (default):** Claude Sonnet 4.6

**Output schema:**
```python
class ExposureAssessment(BaseModel):
    company_id: UUID
    event_id: UUID
    exposure_type: ExposureType
    direction: Direction  # bullish | bearish | neutral
    magnitude: float  # 0-1
    rationale: str
    confidence: float
```

#### Earnings Context Agent

**Purpose:** Before a company's earnings release, synthesize the macro/geo/sector context that will shape interpretation of the results.

**Persona:** A sector specialist preparing notes for a portfolio manager attending the earnings call.

**Tools:** `get_company_earnings_history`, `get_sector_recent_earnings`, `get_macro_indicators`, `get_active_geo_events`, `find_similar_earnings_setups`

**Model (default):** Claude Opus 4.7

#### Event Deep-Dive Agent

**Purpose:** For a single high-impact event (typically triggered by the Reactive Pipeline), produce a thorough analysis: causes, second-order effects, parallels, action implications.

**Persona:** A strategist writing a special situations memo.

**Tools:** All historical and exposure tools, plus `query_related_events`, `get_market_reaction_realtime`

**Model (default):** Claude Opus 4.7

#### Narrative Writer

**Purpose:** Convert structured agent outputs into readable, engaging prose suitable for a Morning Brief or report. Voice and tone matter here.

**Persona:** A financial journalist with a clear, slightly dry voice. Writes like an FT columnist, not like an AI assistant.

**Tools:** `get_user_writing_preferences` (formal/casual), `get_recent_reports` (for stylistic consistency)

**Model (default):** Claude Opus 4.7 (writing quality matters)

#### Q&A Analyst

**Purpose:** Handle interactive user questions ("Why did MSFT drop?", "What if rates go up another 50bps?"). The only agent with looped tool-calling — the others have linear pipelines.

**Persona:** A research analyst on call. Will dig, will speculate carefully, will say "I don't know" when appropriate.

**Tools:** Most of the Tool Library (broadest scope of any agent)

**Model (default):** Claude Opus 4.7

**Special config:** `max_iterations = 10` (other agents typically max 3-5)

### Agent definition file format

Each agent's spec lives in `agents/{role_id}.yaml`:

```yaml
role_id: relevance_analyst
display_name: Relevance Analyst
persona: |
  A senior buy-side analyst who has read 50,000 news items...
system_prompt_file: prompts/relevance_analyst.md
model:
  provider: anthropic
  model_id: claude-sonnet-4-6
  temperature: 0.2
  max_tokens: 2000
tools:
  - get_portfolio_state
  - get_watchlist
  - get_company_exposures
  - query_recent_recommendations
limits:
  max_input_tokens: 8000
  max_iterations: 3
  timeout_seconds: 60
  cost_ceiling_usd: 0.30
confidence_threshold: 0.6
output_schema: schemas/relevance_analysis.py::RelevanceAnalysis
```

Configuration in YAML, prompts in databse (versioned, always use latest version of dedicated prompt - see architecturel requirement - prompt versioning), schemas in Python. All in git. Loaded into the runtime registry on startup.

---

## Section 04 — Tool Library

*The agents' view of the world*

Agents in StokAI never touch raw infrastructure. They call typed business functions from the Tool Library. This is a deliberate constraint: it makes agent behavior predictable, debuggable, and safe.

### Why this constraint matters

Three reasons "agents call business functions, not databases":

1. **Safety.** An agent cannot construct a SQL query that times out the database, cannot accidentally call a paid API in a loop, cannot read another tenant's data.
2. **Consistency.** The same business question always returns the same shape of data. "What is the portfolio exposure to X?" returns a standard `ExposureAssessment`, whether called by Recommendation Synthesizer or Q&A Analyst.
3. **Observability.** Every tool call is logged with its arguments and result. You see exactly what the agent looked at to make its decision.

### Tool taxonomy

Tools are grouped into five families:

#### Portfolio & User Context

| Tool | Returns | Used by |
|---|---|---|
| `get_portfolio_state(tenant_id)` | Current positions, sizes, cost basis | Relevance, Synthesizer |
| `get_watchlist(tenant_id)` | Watchlist companies + reasons added | Relevance, Synthesizer |
| `get_user_preferences(tenant_id)` | Risk profile, writing tone, alert thresholds | Narrative Writer |
| `get_user_history(tenant_id, n)` | Last N reports, recommendations, feedback | Synthesizer, Q&A |

#### Company Data

| Tool | Returns | Used by |
|---|---|---|
| `get_company_fundamentals(ticker)` | Latest fundamentals snapshot | Exposure, Earnings Context |
| `get_company_score_history(company_id, indicator_id, days)` | Score time series | Anomaly Detector, Synthesizer |
| `get_company_volatility(company_id, lookback)` | Realized & implied vol | Anomaly Detector |
| `get_geo_revenue_breakdown(company_id)` | Revenue by country/region | Exposure Analyst |
| `get_supply_chain_dependencies(company_id)` | Known critical dependencies | Exposure Analyst |

#### Events & History

| Tool | Returns | Used by |
|---|---|---|
| `query_recent_events(since, categories, min_intensity)` | Events matching filters | Relevance Analyst |
| `get_event_details(event_id)` | Full event record | Multiple |
| `find_similar_events(event_id, k, time_window)` | Top-K semantic matches via pgvector | Historical Context |
| `get_price_reaction_to_event(event_id, company_id, window)` | Price series T-7d to T+30d | Historical Context |
| `compute_event_outcome_statistics(event_ids, company_id)` | Median, percentiles of reactions | Historical Context |
| `query_related_events(event_id, relationship_type)` | Causally or thematically linked events | Event Deep-Dive |

#### Exposure & Correlation

| Tool | Returns | Used by |
|---|---|---|
| `get_company_exposures(company_id, active_only=True)` | Active exposure records | Relevance, Synthesizer |
| `compute_exposure(company_id, event_id)` | New exposure assessment | Exposure Analyst |
| `get_sector_correlations(sector, lookback)` | Sector return correlations | Exposure Analyst |
| `compute_portfolio_geo_concentration(tenant_id)` | Geographic concentration metrics | Synthesizer |

#### Macro & Market

| Tool | Returns | Used by |
|---|---|---|
| `get_macro_indicators(indicators, lookback)` | FRED series | Earnings Context |
| `get_market_baseline(sector, lookback)` | Sector return distribution | Anomaly Detector |
| `get_active_geo_events(min_intensity, regions)` | Currently-relevant events | Event Deep-Dive |
| `compute_zscore(value, distribution)` | Statistical anomaly score | Anomaly Detector |

#### Memory & Track Record

| Tool | Returns | Used by |
|---|---|---|
| `query_past_recommendations(company_id, days, signal_type)` | Historical recommendations + outcomes | Synthesizer |
| `compute_track_record(role_id, lookback)` | This agent's historical accuracy | Synthesizer |
| `query_semantic_memory(query, namespace)` | Facts learned about entities | Multiple |
| `query_user_feedback(report_type, days)` | What user marked good/bad | Narrative Writer |

### Tool design principles

Every tool follows the same conventions:

1. **Typed inputs and outputs.** Pydantic models. No "JSON blob" returns.
2. **Idempotent and side-effect-free.** Reading tools never mutate state. Writing tools (rare) are explicitly named (`save_recommendation`, not `process`).
3. **Bounded outputs.** Every tool returns at most N rows (default 50). Agents cannot accidentally pull 10,000 rows into context.
4. **Standard error contract.** Tools raise structured errors (`ToolNotApplicable`, `InsufficientData`, `RateLimited`) that agents can reason about.
5. **Cost-aware.** Tools that hit paid APIs are flagged. The orchestrator can enforce cost ceilings per workflow.
6. **Cached when reasonable.** Tool results are cached for the duration of a single workflow run. Calling `get_portfolio_state` three times in one workflow hits the database once.

### Tool registration

```python
# tools/registry.py
TOOL_REGISTRY: dict[str, ToolSpec] = {
    "get_portfolio_state": ToolSpec(
        function=portfolio.get_portfolio_state,
        description="Returns current portfolio: positions, sizes, cost basis.",
        input_schema=GetPortfolioStateInput,
        output_schema=PortfolioState,
        cost_tier=CostTier.FREE,        # no external API
        cache_ttl_seconds=60,
    ),
    "find_similar_events": ToolSpec(
        function=events.find_similar_events,
        description="Returns top-K events semantically similar to the given event.",
        input_schema=FindSimilarEventsInput,
        output_schema=list[SimilarEvent],
        cost_tier=CostTier.COMPUTE,     # pgvector query
        cache_ttl_seconds=3600,
    ),
    # ...
}
```

When an agent is instantiated, it gets exactly the tools listed in its YAML definition. No more, no less.

---

## Section 05 — Memory Subsystem

*The learning loop that makes the system smarter over time*

Long-term memory is what separates "a clever prompt chain" from "a system that gets better." StokAI implements four memory layers, each with different storage, retrieval, and update patterns. All four are built from day 1.

### The four layers

| Layer | What it stores | Retrieval pattern | Update pattern |
|---|---|---|---|
| Episodic | Every workflow run, every decision, every outcome | Filter by time, agent, event | Append-only |
| Semantic | Learned facts about entities (companies, people, events) | Vector + keyword search | Curated extraction |
| Procedural | What reasoning approaches work well in what contexts | Pattern matching | Reinforcement from outcomes |
| User Feedback | Explicit signals from the user (approve/reject/edit) | Filter by report type, time | Direct logging |

### Layer 1 — Episodic Memory

**Purpose:** A complete record of what happened. The system's autobiography.

**Storage:** PostgreSQL tables (`workflow_run`, `agent_invocation`, `tool_call`, `recommendation_outcome`). Indexed for filtering.

**What gets stored:** Every workflow run with its full state. Every agent invocation with its input, output, confidence, cost, latency. Every tool call with arguments and result. Every recommendation with its eventual outcome (filled in ex-post).

**Schema sketch:**
```sql
CREATE TABLE workflow_run (
  workflow_id UUID PRIMARY KEY,
  workflow_type TEXT,
  tenant_id UUID,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  status TEXT,  -- success | failed | requires_hil
  final_state JSONB,
  cost_usd NUMERIC,
  langfuse_trace_id TEXT  -- link to Langfuse
);

CREATE TABLE agent_invocation (
  invocation_id UUID PRIMARY KEY,
  workflow_id UUID REFERENCES workflow_run,
  agent_role_id TEXT,
  node_name TEXT,
  started_at TIMESTAMPTZ,
  duration_ms INT,
  model_used TEXT,
  prompt_version TEXT,  -- Langfuse prompt version
  input_tokens INT,
  output_tokens INT,
  cost_usd NUMERIC,
  confidence NUMERIC,
  output JSONB,
  tools_called JSONB[]
);
```

**Why this matters:** When the user asks "why did the system recommend BUY_OPP on XOM last Tuesday?", you can reconstruct the entire reasoning chain. When evaluating whether a prompt change improved things, you have the baseline. When the system makes a bad call, you can find it and fix it.

**Retention:** Indefinite. Storage is cheap; lost reasoning history is expensive.

### Layer 2 — Semantic Memory

**Purpose:** Curated facts the system has learned about entities. "MSFT's CEO tends to soften guidance in down quarters" or "Brent crude futures react more strongly to Strait of Hormuz events than to broader Gulf tensions."

**Storage:** PostgreSQL table `semantic_fact` with pgvector embeddings for retrieval.

```sql
CREATE TABLE semantic_fact (
  fact_id UUID PRIMARY KEY,
  namespace TEXT,           -- "company:MSFT", "event_type:fed_announcement"
  fact_text TEXT,           -- "Tends to soften guidance in down quarters"
  evidence_count INT,       -- how many observations support this
  confidence NUMERIC,       -- 0-1
  first_observed TIMESTAMPTZ,
  last_confirmed TIMESTAMPTZ,
  embedding VECTOR(1536),
  source_invocations UUID[] -- which agent runs produced this fact
);
```

**Why curated, not automatic:** This is where most agentic memory systems fail. They let agents write arbitrary "facts" to memory and within weeks the memory is contaminated with hallucinations. We avoid this by:

1. **Facts only enter semantic memory through explicit extraction.** A scheduled job (weekly) examines episodic memory, identifies patterns confirmed across multiple runs, and proposes new facts.
2. **Proposed facts require evidence count ≥ 3** before being committed.
3. **Facts decay if not reconfirmed.** A fact unconfirmed for 6 months has its confidence reduced.
4. **Facts can be explicitly retracted** by the user via the HIL interface.

**Retrieval:** Agents query semantic memory through the `query_semantic_memory(query, namespace)` tool. Top-K results by vector similarity, filtered by confidence threshold.

### Layer 3 — Procedural Memory

**Purpose:** What reasoning approaches work. "When analyzing Fed announcements, looking at the 2-year yield reaction within 90 seconds is more predictive than the headline rate." Meta-knowledge.

**Storage:** PostgreSQL table `procedural_pattern` linked to episodic outcomes.

```sql
CREATE TABLE procedural_pattern (
  pattern_id UUID PRIMARY KEY,
  context_signature TEXT,     -- "event_category=fed_announcement"
  approach_description TEXT,  -- "weight 2y yield reaction > rate level"
  success_rate NUMERIC,       -- measured against actual outcomes
  sample_size INT,
  confidence NUMERIC,
  recommended_for_agents TEXT[]  -- which agent roles should consider this
);
```

**Why this is the hardest layer:** It is essentially the system attempting to learn its own meta-strategy. Honest assessment: in v1, this layer is mostly read-only (it gets used by agents but rarely written to automatically). In v2-v3, we build the offline analysis pipeline that mines episodic memory for procedural patterns.

**v1 bootstrapping:** Seed with hand-authored patterns based on domain expertise. Track which patterns get used and how often they correlate with successful outcomes.

**v2 automation:** Weekly job that examines episodic memory + outcomes, identifies recurring (context, approach, outcome) triples, proposes new procedural patterns. Patterns require manual review before activation.

### Layer 4 — User Feedback

**Purpose:** Explicit user signals. This is the highest-value training data because it's direct ground truth from the person the system is built for.

**Storage:** PostgreSQL table `user_feedback`.

```sql
CREATE TABLE user_feedback (
  feedback_id UUID PRIMARY KEY,
  tenant_id UUID,
  report_id UUID,             -- which report
  recommendation_id UUID,     -- optional: which specific recommendation
  feedback_type TEXT,         -- approve | reject | edit | thumbs_up | thumbs_down
  feedback_text TEXT,         -- optional user comment
  user_edit TEXT,             -- if they edited, the new version
  submitted_at TIMESTAMPTZ
);
```

**Sources of feedback:**
- HIL queue actions (approve/edit/reject)
- Thumbs up/down on recommendations in the UI
- Reply-with-comment on email reports
- Implicit: "user clicked through to company X within 5 minutes of receiving brief" (engagement signal)

**How it's used:**
- **Immediate:** Rejected reports are NOT sent. Edited reports are sent in their edited form.
- **Short-term:** Recent rejections inform the next workflow run ("the last 3 Morning Briefs you rejected were over-emphasizing geopolitical risk — calibrate")
- **Long-term:** Feedback becomes labels for golden datasets (Section 09). Approved high-confidence reports → positive examples. Rejected reports → negative examples. Edits → "needs improvement" with ground truth.

### How agents use memory

A representative call from an agent's perspective:

```python
# Inside Recommendation Synthesizer
async def synthesize(state: WorkflowState):
    # Episodic: what have we recommended for this company recently?
    past_recs = await tools.query_past_recommendations(
        company_id=state.target_company,
        days=30
    )

    # Semantic: what do we know about this company?
    facts = await tools.query_semantic_memory(
        query=f"behavior patterns for {state.target_company.ticker}",
        namespace=f"company:{state.target_company.ticker}"
    )

    # Procedural: what approach works for this context?
    patterns = await tools.query_procedural_patterns(
        context_signature=build_context_sig(state)
    )

    # User feedback: what did the user think of recent similar reports?
    feedback = await tools.query_user_feedback(
        report_type="morning_brief",
        days=14
    )

    # All four layers feed the synthesis
    recommendation = llm.generate(
        prompt=load_prompt("recommendation_synthesizer"),
        context={
            "past_recs": past_recs,
            "facts": facts,
            "patterns": patterns,
            "feedback": feedback,
            "state": state,
        }
    )
    return recommendation
```

### Memory hygiene

Three guardrails against memory becoming a liability:

1. **Quarterly review.** A scheduled task surfaces low-confidence semantic facts for manual review.
2. **Decay functions.** Facts and patterns not reconfirmed for N months have their confidence reduced.
3. **Explicit retraction.** The user can mark any fact, pattern, or feedback record as wrong, which removes it from retrieval.

---

## Section 06 — Quality Control & Human-in-the-Loop

*Catching bad outputs before they reach the user*

The system has confidence in everything it produces. Below a threshold, the user becomes the final reviewer. This is not a limitation — it is the feedback loop that makes the system improve.

### The confidence model

Every agent output carries a `confidence` field in [0, 1]. This is not magic — it's computed deliberately:

```python
def compute_confidence(agent_output, context) -> float:
    base = 0.5

    # Evidence strength
    if context.sample_size >= 20: base += 0.2
    elif context.sample_size >= 10: base += 0.1
    elif context.sample_size < 3: base -= 0.3

    # Internal consistency (does the agent's reasoning hold together?)
    if has_internal_contradictions(agent_output): base -= 0.2

    # Data freshness
    if context.data_age_hours > 24: base -= 0.1

    # Tool failures during reasoning
    if context.failed_tool_calls > 0: base -= 0.1 * context.failed_tool_calls

    # Historical track record of this agent in similar contexts
    track_record = get_agent_track_record(agent_role, context.signature)
    base += (track_record - 0.5) * 0.3

    return clip(base, 0.0, 1.0)
```

Confidence is calibrated against ex-post outcomes (Section 09, Tier 3). If "high confidence" recommendations don't actually outperform "medium confidence" ones, the confidence model is broken and gets fixed.

### Workflow-level confidence

A workflow has overall confidence equal to the minimum confidence of its critical AgentNodes. If the Recommendation Synthesizer reports 0.85 confidence but the Historical Context Agent reports 0.4 (small sample), the workflow's overall confidence is 0.4.

Configurable per workflow type:

```yaml
# workflows/morning_brief.yaml
confidence_thresholds:
  auto_send: 0.7        # ≥0.7 → send without review
  hil_queue: 0.4        # 0.4-0.7 → review queue
  do_not_send: 0.4      # <0.4 → block, log, learn
```

### The HIL Review Queue

When a workflow output falls into the `hil_queue` band, it goes to a web UI for review before delivery.

**Queue UI:**
- List of pending items sorted by scheduled send time
- Each item shows: report preview, confidence breakdown by node, key concerns flagged, time-to-send countdown
- Actions: **Approve** (send as-is), **Edit & Approve** (modify and send), **Reject** (don't send), **Reject with feedback** (don't send + explain why)

**Timing model:**

| Workflow | Scheduled send | HIL window | Fallback |
|---|---|---|---|
| Morning Brief | 06:00 | 22:00 prev → 05:45 | If unreviewed at 05:45: hold, notify user there's something to review |
| On-demand Analysis | User-initiated | User waits | If unreviewed in 10 min: deliver with prominent low-confidence banner |
| Watchlist Scan | 18:00 | 14:00 → 17:45 | Same as Morning Brief |
| Earnings Risk Brief | T-1 day 18:00 | 14:00 → 17:45 | Same as Morning Brief |
| Event Deep-Dive | Event-driven | 30 min from generation | Send with low-confidence banner |

**Why a web queue and not auto-send-with-warning:** Two reasons. First, your quality-first ranking — you'd rather delay a report by hours than ship a bad one. Second, every HIL decision is high-value training data; capturing it in a structured form (approve/edit/reject + reason) compounds over time.

### The feedback loop

Every HIL action writes to user feedback memory (Layer 4):

```
Approve as-is        → "this calibration was right"
Edit & Approve       → "almost right, here's the correction"
Reject with reason   → "this kind of output is wrong because X"
```

These accumulate. Weekly, an offline job:

1. Aggregates feedback patterns ("you rejected 4 of last week's geo-heavy briefs")
2. Generates proposed prompt or threshold adjustments
3. Surfaces them in the UI for your review
4. On approval, the changes are committed via the standard prompt versioning flow (Section 10)

This is how the system learns. Not through magical autonomous self-improvement, but through structured capture of your judgment, surfaced as actionable proposals.

---

## Section 07 — LangGraph Implementation

*How this maps to the framework*

LangGraph was chosen for its graph-based execution model, observability, and Python-native fit. Here is how StokAI's concepts map to LangGraph primitives.

### Mapping table

| StokAI concept | LangGraph primitive |
|---|---|
| Workflow | `StateGraph` |
| WorkflowState | The graph's state schema (Pydantic model) |
| DeterministicNode | A node function: `(state) -> state` |
| AgentNode | A node function that wraps an agent invocation |
| Conditional branching | `add_conditional_edges` |
| Parallel sub-workflows | Multiple edges from one node + state merging |
| Retries | Node-level retry policy + LangGraph checkpointing |
| Long-running workflows | LangGraph persistence + checkpointing |

### Code skeleton — Morning Brief

```python
from langgraph.graph import StateGraph, END
from stokai.workflows.state import WorkflowState
from stokai.agents import invoke_agent
from stokai.nodes import deterministic

def build_morning_brief_graph() -> StateGraph:
    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("fetch_portfolio", deterministic.fetch_portfolio_state)
    graph.add_node("fetch_events", deterministic.fetch_overnight_events)
    graph.add_node("relevance_analysis", lambda s: invoke_agent("relevance_analyst", s))
    graph.add_node("recompute_scores", deterministic.recompute_scores)
    graph.add_node("anomaly_detection", lambda s: invoke_agent("anomaly_detector", s))
    graph.add_node("historical_context", lambda s: invoke_agent("historical_context_agent", s))
    graph.add_node("synthesize", lambda s: invoke_agent("recommendation_synthesizer", s))
    graph.add_node("write_narrative", lambda s: invoke_agent("narrative_writer", s))
    graph.add_node("evaluate_quality", deterministic.evaluate_quality)
    graph.add_node("route_to_hil", deterministic.send_to_hil_queue)
    graph.add_node("format_email", deterministic.render_email)
    graph.add_node("dispatch", deterministic.send_email)

    # Linear flow
    graph.set_entry_point("fetch_portfolio")
    graph.add_edge("fetch_portfolio", "fetch_events")
    graph.add_edge("fetch_events", "relevance_analysis")
    graph.add_edge("relevance_analysis", "recompute_scores")
    graph.add_edge("recompute_scores", "anomaly_detection")
    graph.add_edge("anomaly_detection", "historical_context")
    graph.add_edge("historical_context", "synthesize")
    graph.add_edge("synthesize", "write_narrative")
    graph.add_edge("write_narrative", "evaluate_quality")

    # Conditional: HIL or auto-send
    graph.add_conditional_edges(
        "evaluate_quality",
        condition=lambda s: "route_to_hil" if s.requires_hil else "format_email",
    )

    graph.add_edge("route_to_hil", END)  # HIL UI takes over
    graph.add_edge("format_email", "dispatch")
    graph.add_edge("dispatch", END)

    return graph.compile(checkpointer=postgres_checkpointer)
```

### Why checkpointing matters

LangGraph supports checkpointing every node's output to persistent storage. Three reasons this is non-negotiable for StokAI:

1. **Failure recovery.** If the Historical Context agent times out, we don't redo the Relevance Analysis. We resume from the checkpoint.
2. **HIL pause.** When a workflow goes to HIL, the graph is paused, not killed. On approval, it resumes from the next node.
3. **Replay for debugging.** When investigating a bad output, you can re-run from any checkpoint with a new prompt version or model.

Checkpointer: PostgreSQL (we already have it).

### Parallelism within a workflow

Some workflows benefit from parallel execution. Example: the Historical Context step has to find analogies for each relevant event — these are independent.

```python
# Inside Historical Context node
async def run(state: WorkflowState) -> WorkflowState:
    tasks = [
        invoke_agent("historical_context_agent", state, event=e)
        for e in state.relevant_events
    ]
    results = await asyncio.gather(*tasks)
    state.analogies = {r.event_id: r.analogies for r in results}
    return state
```

Parallel agent invocations are subject to the same cost ceilings and observability. Langfuse traces them as sibling spans under the same parent.

### Bounded execution

Every node has explicit bounds:

```yaml
node_defaults:
  timeout_seconds: 60
  max_retries: 2
  cost_ceiling_usd: 0.50

agent_node_overrides:
  recommendation_synthesizer:
    timeout_seconds: 120  # this one can think longer
    cost_ceiling_usd: 1.00
  qa_analyst:
    timeout_seconds: 180  # interactive Q&A, loops allowed
    max_iterations: 10
```

When a bound is exceeded, the node fails fast. The workflow either retries (per policy) or routes to error handling.

---

## Section 08 — Observability Stack

*Full overview of every LLM decision*

Observability for an agentic system requires three layers most APM tools don't capture: traces of LLM decisions, the reasoning behind them, and evaluation of whether they were correct. The stack: **Langfuse, self-hosted, from day 1.**

### Why Langfuse

Three reasons specific to StokAI:

1. **Self-host without enterprise pricing.** Aligns with the master architecture's "no hard cloud lock-in" principle. Owns the data, no vendor lock-in surprise.
2. **Framework-agnostic with strong LangGraph support.** OTEL-compatible, integrates cleanly with LangGraph's native tracing.
3. **Integrated tracing + prompt management + evaluation + datasets in one product.** Fewer moving parts, less operational overhead for a small team.

The alternative we explicitly rejected: **LangSmith.** It has the deepest LangGraph integration in the industry — but self-hosting is enterprise-only, which violates the master architecture's portability principle.

### Deployment

Langfuse runs as containers alongside the application:

```yaml
# docker-compose.yml additions
services:
  langfuse-server:
    image: langfuse/langfuse:latest
    depends_on: [langfuse-db, clickhouse]
    environment:
      DATABASE_URL: postgresql://langfuse-db:5432/langfuse
      CLICKHOUSE_URL: http://clickhouse:8123
      NEXTAUTH_SECRET: ${LANGFUSE_AUTH_SECRET}
      NEXTAUTH_URL: ${LANGFUSE_URL}
    ports:
      - "3000:3000"

  langfuse-db:
    image: postgres:16
    volumes:
      - langfuse-db-data:/var/lib/postgresql/data

  clickhouse:
    image: clickhouse/clickhouse-server:latest
    volumes:
      - clickhouse-data:/var/lib/clickhouse
```

Cost in Azure: roughly $15-30/month for the additional containers + storage. Trivial relative to the value of full LLM decision auditability.

### The four pillars of observability

#### Pillar 1 — Trace everything, structured

Every workflow run produces one hierarchical trace:

```
Trace: morning_brief_run_2026-05-29T06:00:00Z
├── Span: fetch_portfolio (deterministic, 120ms)
├── Span: fetch_events (deterministic, 800ms)
├── Span: relevance_analysis (agent)
│   ├── Generation: claude-sonnet-4-6, prompt v17, 3200 in / 800 out tokens, $0.04
│   ├── Tool call: get_portfolio_state (8ms)
│   ├── Tool call: get_watchlist (12ms)
│   └── Tool call: get_company_exposures (45ms)
├── Span: recompute_scores (deterministic, 2.1s)
├── Span: anomaly_detection (agent) ...
├── Span: historical_context (agent)
│   ├── Sub-span: for event A
│   ├── Sub-span: for event B
│   └── Sub-span: for event C
├── Span: synthesize (agent)
└── Span: dispatch (deterministic)

Total: 47 spans · 4m 12s · $1.83 · confidence 0.78 · sent without HIL
```

**Standard metadata on every span:**

| Field | Purpose |
|---|---|
| `workflow_id` | Group all spans of one workflow run |
| `workflow_type` | Filter by workflow (Morning Brief, Watchlist Scan, etc.) |
| `tenant_id` | Multi-tenant slicing |
| `user_id` | Per-user analytics |
| `agent_role_id` | Filter by which agent did the work |
| `prompt_version` | Which prompt version produced this output (link to Langfuse prompt) |
| `model_used` | claude-opus-4-7, claude-sonnet-4-6, etc. |
| `confidence` | Numeric confidence score |
| `cost_usd` | Cost of this span |
| `tokens_in`, `tokens_out` | Token counts |
| `latency_ms` | Span duration |
| `tools_called` | Array of tool names invoked |
| `state_snapshot_ref` | Pointer to the WorkflowState at this point (for replay) |

Filtering example: "Show me all Recommendation Synthesizer runs in the last week where confidence < 0.6 AND cost > $0.80." This kind of diagnostic query is one filter in the Langfuse UI.

#### Pillar 2 — Prompt management as code

Every agent's system prompt lives as a versioned artifact, accessed by Langfuse SDK:

```python
# In the agent invocation
prompt = langfuse.get_prompt(
    name="relevance_analyst",
    label="production"  # or specific version
)
system_prompt = prompt.compile(
    portfolio_size=len(state.portfolio),
    market_tone=state.market_tone_signal,
)
# The version used is automatically attached to the trace
```

**Why this matters:**

- **Edit without redeploying the app.** Iterate at the speed of thought during MVP.
- **Every change is a version.** "v17 ran from May 15-22, v18 from May 22-now." Compare results in Langfuse.
- **Production traces link back to the prompt version.** "Why did this report suck?" → "It ran on v15, which had a bug. Roll back to v14."

Source of truth in git (Section 10), deployed to Langfuse via CI.

#### Pillar 3 — Evaluation built into the loop

Every Recommendation Synthesizer output is automatically scored by an LLM-as-judge running in the background. Every dataset experiment runs through the same evaluator framework. Every workflow's outcome (the actual market reaction) is logged back as ground truth. Detailed in Section 09.

#### Pillar 4 — Datasets curated from production

Every HIL action and user feedback signal becomes a labeled example. Langfuse natively supports building datasets from production traces:

- Approved high-confidence reports → "gold standard" dataset
- Rejected reports → "negative examples" dataset
- Edited reports → "needs improvement" dataset (with edits as ground truth)
- Ex-post wrong recommendations → "what went wrong" dataset

These datasets are the regression suite for every prompt change.

### Querying observability

Three personas, three query patterns:

**Developer debugging a specific run:**
"Why did this Morning Brief produce a BUY_OPP on TSLA when the user has no position?"
→ Open the trace in Langfuse, walk down the span tree, see exactly which agent saw what input and produced what output. Every prompt is visible, every tool call is logged.

**Product owner monitoring quality:**
"How is overall report quality trending?"
→ Langfuse dashboard with: % HIL approval rate, mean confidence, LLM-judge score distribution, ex-post calibration (Tier 3) accuracy. All filterable by workflow type, agent role, prompt version.

**Cost owner monitoring spend:**
"Why was last week's AI bill $40 higher than usual?"
→ Filter spans by cost > median, group by workflow type and agent role. Common answer: "the Earnings Context agent looped 8 times on a complex case." Tighten the iteration ceiling.

### What this is NOT

Two important non-goals:

- **Not a replacement for application monitoring.** Langfuse handles LLM-specific observability. Standard APM (logs, infra metrics, error tracking) lives separately — Azure Monitor or Prometheus per the master architecture.
- **Not a debugging tool for arbitrary bugs.** Langfuse is excellent for "why did this agent decide X." For "why did this database query fail," use database monitoring.

---

## Section 09 — Evaluation Framework

*How we know if the system is good — and getting better*

Observability tells you what happened. Evaluation tells you whether it was right. Without rigorous evaluation, agentic systems silently degrade and nobody notices for months.

StokAI runs all three evaluation tiers from MVP. This is ambitious, but the master architecture's "quality > cost" ranking demands it.

### The three tiers

| Tier | What it measures | Frequency | Cost | Latency |
|---|---|---|---|---|
| 1. Online LLM-as-judge | Per-output quality on production runs | Every output | $0.01-0.03 per eval | Async, ~5s |
| 2. Golden dataset regression | Quality on a fixed test set | Every prompt change | $1-3 per full run | Manual trigger, ~5 min |
| 3. Ex-post calibration | Recommendations vs actual market outcomes | Continuous (T+1d, T+1w) | Free (data already collected) | Asynchronous |

### Tier 1 — Online LLM-as-judge

Every output of agents whose work is user-facing (Recommendation Synthesizer, Narrative Writer, Event Deep-Dive Agent) gets evaluated by a separate LLM running as a judge.

**Setup:**

```python
# evaluators/recommendation_judge.py
JUDGE_PROMPT = load_prompt("evaluators/recommendation_judge")

async def evaluate_recommendation(trace_id: str, output: RecommendationSet):
    judge_output = await langfuse_judge(
        model="claude-opus-4-7",  # different model from producer
        prompt=JUDGE_PROMPT,
        input={
            "recommendation": output.dict(),
            "context": fetch_trace_context(trace_id),
        }
    )
    # Returns structured scores
    await langfuse.score(
        trace_id=trace_id,
        name="factual_grounding",
        value=judge_output.factual_grounding,
    )
    await langfuse.score(
        trace_id=trace_id,
        name="confidence_calibration",
        value=judge_output.confidence_calibration,
    )
    await langfuse.score(
        trace_id=trace_id,
        name="internal_consistency",
        value=judge_output.internal_consistency,
    )
```

**Dimensions scored:**

- **Factual grounding (0-1):** Does every claim in the recommendation reference data that was actually retrieved by tools? Or is the agent making things up?
- **Confidence calibration (0-1):** Is the stated confidence appropriate given the evidence cited?
- **Internal consistency (0-1):** Are the conclusions logically consistent with the rationale?
- **Tool use appropriateness (0-1):** Did the agent use the right tools for the question, or did it skip available evidence?

**What we DON'T evaluate with LLM-as-judge:** Whether the recommendation will be profitable. That's Tier 3 territory — judge LLMs cannot predict markets, and asking them to do so is a category error.

**Cost guardrails:** Tier 1 evals cost ~$0.01-0.03 each. At ~10 Morning Briefs/day × 1 user × 4 evaluations per brief = $0.40-1.20/day in MVP. At 50 users: ~$20-60/day. Budgeted explicitly.

### Tier 2 — Golden Dataset Regression

A hand-curated set of ~50 historical events with expected analysis characteristics. Every prompt change or model change runs against this set before being promoted.

**Bootstrapping:** ~1 week of manual effort to assemble. For each event in the set:
- Full context (timestamp, data available at the time)
- Expected relevant tickers and sectors
- Expected recommendation direction (with rationale)
- Notes on edge cases or known difficulties

**Storage:** Langfuse Datasets feature. Each example versioned, labeled by difficulty and category.

**Execution:**

```bash
# CI step on every prompt change
stokai eval run \
  --dataset golden_events_v3 \
  --workflow event_deep_dive \
  --prompt-version $GIT_SHA \
  --report-to langfuse
```

**Gate:** A prompt change cannot be promoted to production if it scores worse than current production on the golden dataset by more than 5% on any metric. Hard gate, no overrides without explicit acknowledgment.

**Expansion:** The dataset grows over time from:
- HIL queue rejections (every rejected report becomes a negative example)
- HIL queue edits (every edited report becomes a "production was wrong, here's what was right" example)
- Notable historical events the user flags as "should have caught this"

### Tier 3 — Ex-post Calibration (the real evaluator)

This is the unique-to-StokAI tier. For every recommendation, we have `actual_t1d`, `actual_t1w`, etc. filled in T+1 day, T+1 week (from `price_bar`). Over time this becomes a calibrated track record.

**The calibration question:** Did our "HIGH confidence BULLISH" recommendations actually outperform "LOW confidence BULLISH" ones?

```sql
-- Tier 3 calibration query
SELECT
    confidence_bucket,  -- 0.0-0.2, 0.2-0.4, ..., 0.8-1.0
    signal_type,
    COUNT(*) as n,
    AVG(actual_t1d) as mean_return_1d,
    AVG(actual_t1w) as mean_return_1w,
    STDDEV(actual_t1d) as vol_1d,
    -- The key calibration metric:
    CORR(confidence, actual_t1d * direction_sign) as confidence_correlation
FROM ai_recommendation
WHERE generated_at > NOW() - INTERVAL '90 days'
  AND actual_t1d IS NOT NULL
GROUP BY confidence_bucket, signal_type
ORDER BY confidence_bucket, signal_type;
```

**What good calibration looks like:**
- High-confidence BULLISH recommendations: mean T+1d return clearly positive
- Low-confidence BULLISH recommendations: mean T+1d return weakly positive or zero
- Confidence buckets correlate monotonically with realized direction
- `confidence_correlation` significantly positive

**What broken calibration looks like:**
- High-confidence recommendations no more accurate than low-confidence ones → confidence model is meaningless
- All recommendations cluster at one confidence level → confidence model not discriminating
- Direction predictions worse than 50/50 → fundamental quality problem

**Acting on calibration data:**

| Pattern | Response |
|---|---|
| Calibration drifts over months | Investigate which agent changed; consider model regression |
| One signal type (e.g., CONTRARIAN) systematically wrong | Audit Recommendation Synthesizer's CONTRARIAN logic |
| Confidence doesn't discriminate | Rework the confidence computation; gather feedback samples |
| Specific event categories underperform | Specialized agent prompt for that category |

**Dashboard:** A Langfuse dashboard with calibration plots, updated daily. Looked at weekly minimum.

### Continuous improvement loop

The three tiers connect:

```
Tier 3 surfaces: "CONTRARIAN signals on energy stocks are systematically wrong"
   ↓
Investigation: which prompts/agents produce CONTRARIAN energy calls?
   ↓
Hypothesis: Recommendation Synthesizer over-weights historical analogies in commodity-exposed sectors
   ↓
Tier 2: Update the prompt, run against golden dataset (subset: energy events)
   ↓
Compare: new prompt vs current production on golden set
   ↓
If improvement, deploy to production with prompt versioning
   ↓
Tier 1 (online judge) confirms no regression on other dimensions
   ↓
Tier 3 monitors whether the fix actually improved real-world calibration
```

This is the learning loop. Every tier feeds the others. The system improves not by autonomous magic but by structured human investigation guided by data the system itself collects.

---

## Section 10 — Prompt Management

*Hybrid: git for truth, Langfuse for runtime*

Prompts are the agents' identity. They deserve the same care as code: version control, code review, testing, traceability.

### The hybrid model

**Source of truth: git.** Every prompt lives as a Markdown file in the repository.

```
/prompts
├── agents/
│   ├── relevance_analyst.md
│   ├── anomaly_detector.md
│   ├── historical_context_agent.md
│   ├── recommendation_synthesizer.md
│   ├── exposure_analyst.md
│   ├── earnings_context_agent.md
│   ├── event_deep_dive_agent.md
│   ├── narrative_writer.md
│   └── qa_analyst.md
├── evaluators/
│   ├── recommendation_judge.md
│   ├── factuality_judge.md
│   └── calibration_judge.md
└── classifiers/  (used by Reactive Pipeline, no agent persona)
    ├── event_classifier.md
    ├── tweet_classifier.md
    └── ticker_extractor.md
```

**Runtime: Langfuse.** A CI step publishes prompts to Langfuse with the git SHA as the version tag:

```bash
# CI on merge to main
stokai prompts sync --git-sha $GITHUB_SHA --langfuse-env production
```

At runtime, agents pull from Langfuse:

```python
prompt = langfuse.get_prompt(
    name="relevance_analyst",
    label="production"  # always latest production
)
# The version (git SHA) is automatically logged with every trace
```

### Why hybrid and not pure-Langfuse

Several reasons:

1. **Code review.** Prompt changes go through PR review. A change to `recommendation_synthesizer.md` is reviewed like any code change.
2. **Disaster recovery.** If Langfuse data is lost or corrupted, prompts are recoverable from git.
3. **Reproducibility.** Any historical state of the system can be reconstructed: `git checkout <sha>` gives you the prompts that ran then.
4. **Diff and merge.** Standard tools for reviewing changes. Prompt-management UIs are awkward at this.

### Why hybrid and not pure-git

1. **Production iteration speed.** Tiny adjustments (a word change, a calibration tweak) can be promoted to a Langfuse "preview" label, tested live on one user, and rolled back instantly. Without git PR overhead for experiments.
2. **Trace linkage.** Langfuse can link a production trace directly to the prompt version that produced it, with one click. Git can't.
3. **A/B testing.** Langfuse supports multiple labels (`production`, `experimental`, `champion`, `challenger`). Easy to run prompt experiments without code changes.

### Prompt file format

Each prompt is a Markdown file with frontmatter:

```markdown
---
agent: relevance_analyst
description: Filters overnight events for portfolio relevance
input_variables:
  - portfolio_size
  - market_tone_signal
  - watchlist_size
model_recommendation: claude-sonnet-4-6
temperature_recommendation: 0.2
last_reviewed: 2026-05-15
reviewed_by: user
---

# Role

You are a senior buy-side analyst with 15 years of experience...

# Task

Given a list of overnight events and the user's current portfolio + watchlist, identify which events are genuinely relevant...

# Inputs

- Portfolio: {portfolio_size} positions
- Watchlist: {watchlist_size} companies
- Overall market tone: {market_tone_signal}
- Events to evaluate: (provided in tool output)

# What "relevant" means

[Detailed criteria...]

# What to exclude

[Anti-criteria...]

# Output format

[Structured output specification...]

# Examples

[2-3 worked examples showing the kind of reasoning expected]
```

### Promotion workflow

A new or modified prompt goes through:

1. **Draft.** Engineer modifies the `.md` file locally. Iterates against a small test set.
2. **PR.** Pull request includes the prompt change + a results report (Tier 2 golden dataset run from the dev branch).
3. **Review.** Code review focused on: prompt clarity, anti-patterns avoided, examples valid.
4. **Merge.** On merge, CI publishes to Langfuse with label `staging` and git SHA as version.
5. **Canary.** Promoted to label `canary` on a small fraction of production traffic (initially just your own usage).
6. **Tier 1 + Tier 3 monitor.** Online judge and ex-post calibration on canary traffic vs production.
7. **Promotion.** After N days (configurable per agent), if metrics hold, promoted to label `production`.

### Rollback

A regression detected post-promotion:

```bash
stokai prompts rollback --agent recommendation_synthesizer --to-version <previous_sha>
```

This re-labels the previous version as `production`. Effective within seconds, no deployment needed. The git history is preserved either way.

---

## Section 11 — The Five Core Workflows

*Fully documented for the design partner*

Each workflow is a LangGraph instance with its specific topology. They all follow the DeterministicNode/AgentNode pattern, share the Tool Library and Memory Subsystem, and produce structured outputs.

### Workflow 1 — Morning Brief

**Trigger:** Daily cron at 05:30 (target send: 06:00). One run per user.

**Purpose:** A personalized overview of overnight market activity with recommendations for portfolio and watchlist.

**Graph:**

```
[fetch_portfolio]              ← deterministic
       ↓
[fetch_overnight_events]       ← deterministic, last 12h
       ↓
[Relevance Analyst]            ← AGENT, filter to what matters
       ↓
[recompute_scores]             ← deterministic, update scores with overnight data
       ↓
[Anomaly Detector]             ← AGENT, identify unusual moves
       ↓
[Historical Context Agent]     ← AGENT, parallel per relevant event
       ↓
[Recommendation Synthesizer]   ← AGENT, the capstone
       ↓
[Narrative Writer]             ← AGENT, prose output
       ↓
[evaluate_quality]             ← deterministic, compute overall confidence
       ↓
        ┌─ confidence ≥ 0.7 ─→ [format_email] → [dispatch]
        └─ confidence < 0.7 ─→ [route_to_hil]
```

**Budget:** Target 4-5 minutes, $1.50-2.00 per run.

**Key state outputs:** `report` artifact, recommendations per company, narrative text.

**HIL behavior:** Confidence < 0.7 queues report for review. If unreviewed by 05:45, holds and notifies user.

### Workflow 2 — On-Demand Company Analysis

**Trigger:** User clicks "Deep analyze this company" in UI.

**Purpose:** A thorough analysis of a single company in current context — fundamentals, geo exposure, technical setup, historical analogies, recommendation.

**Graph:**

```
[fetch_company_state]          ← deterministic, current data
       ↓
[fetch_active_events]          ← deterministic, events touching this company
       ↓
[Exposure Analyst]             ← AGENT, exposure to each active event
       ↓
[Historical Context Agent]     ← AGENT, similar past situations for this company
       ↓
[Anomaly Detector]             ← AGENT, is current state unusual?
       ↓
[Recommendation Synthesizer]   ← AGENT
       ↓
[Narrative Writer]             ← AGENT
       ↓
[evaluate_quality + branch]
```

**Budget:** 3-4 minutes, $1.00-1.50.

**Difference from Morning Brief:** Single-company focus, no portfolio-wide filtering, deeper exposure analysis.

### Workflow 3 — Watchlist Scan

**Trigger:** Daily cron at 17:30 (target send: 18:00, before US market close).

**Purpose:** Identify the most actionable watchlist opportunities going into the close and overnight.

**Graph:**

```
[fetch_watchlist]              ← deterministic
       ↓
[fetch_today_events]           ← deterministic, intraday
       ↓
[Relevance Analyst]            ← AGENT, which watchlist names did today's events touch?
       ↓
[recompute_scores]             ← deterministic
       ↓
[Anomaly Detector]             ← AGENT, which watchlist scores moved meaningfully?
       ↓
[Historical Context Agent]     ← AGENT, only for high-anomaly names
       ↓
[Recommendation Synthesizer]   ← AGENT, prioritize top N opportunities
       ↓
[Narrative Writer]             ← AGENT
       ↓
[evaluate_quality + branch]
```

**Budget:** 3 minutes, $1.00.

**Difference from Morning Brief:** Watchlist-only, focused on actionability ("what should I consider buying or sizing into before close"), shorter narrative.

### Workflow 4 — Earnings Risk Brief

**Trigger:** Daily cron. For each portfolio company with earnings in T+1 day at 17:30.

**Purpose:** Synthesize macro/geo/sector context that will shape interpretation of the earnings release.

**Graph:**

```
[fetch_company_state]                  ← deterministic
       ↓
[fetch_earnings_history]               ← deterministic, last 8 quarters
       ↓
[fetch_macro_context]                  ← deterministic, FRED indicators
       ↓
[fetch_sector_recent_earnings]         ← deterministic, sector peers' recent reports
       ↓
[Earnings Context Agent]               ← AGENT, synthesizes the setup
       ↓
[Historical Context Agent]             ← AGENT, similar earnings setups
       ↓
[Recommendation Synthesizer]           ← AGENT, scenario tree
       ↓
[Narrative Writer]                     ← AGENT
       ↓
[evaluate_quality + branch]
```

**Budget:** 4 minutes, $1.50.

**Unique aspects:** Heavy use of Earnings Context Agent (specialized role); produces scenario tree (beat/in-line/miss outcomes) rather than directional recommendation.

### Workflow 5 — Event Deep-Dive

**Trigger:** Reactive Pipeline detects a high-intensity event affecting the portfolio. Enqueues this workflow to run asynchronously.

**Purpose:** Within ~10 minutes of the event, produce a thorough analysis far richer than the initial alert.

**Graph:**

```
[fetch_event_full]                     ← deterministic, all enrichment
       ↓
[fetch_market_reaction_so_far]         ← deterministic, price action since event
       ↓
[Exposure Analyst]                     ← AGENT, parallel per affected portfolio company
       ↓
[Event Deep-Dive Agent]                ← AGENT, causes, second-order effects, analogies
       ↓
[Historical Context Agent]             ← AGENT, similar past events
       ↓
[Recommendation Synthesizer]           ← AGENT, action implications
       ↓
[Narrative Writer]                     ← AGENT
       ↓
[evaluate_quality + branch]
```

**Budget:** 5-7 minutes, $2.00.

**Unique aspects:** Triggered by Mode A handoff (Section 12). Event Deep-Dive Agent is unique to this workflow. Produces a "memo" artifact rather than a brief.

### Cross-workflow patterns

Several patterns recur:

- **`evaluate_quality` is always the second-to-last deterministic node.** It computes overall confidence, sets `requires_hil`, and routes accordingly.
- **`Narrative Writer` is always last among agents.** Its job is converting structured analyses into readable prose. Keeps voice consistent across workflows.
- **`Historical Context Agent` is reused everywhere.** It's the most-used agent in the system, which is why it has its own Tier 2 dataset.
- **Parallelism appears in `Exposure Analyst` and `Historical Context Agent`.** When the input is a list (events, companies), the agent invocations run in parallel.

---

## Section 12 — The Reactive Pipeline

*Non-agentic real-time path*

The Reactive Pipeline handles real-time events where speed and predictability matter more than analytical depth. It is deliberately non-agentic.

### Structure

A fixed sequence of nodes, each either deterministic code or a single scoped LLM call. No tools, no loops, no branching.

```
[1] Event arrives (webhook / poll / stream)
     ↓
[2] persist_raw_event              ← deterministic
     ↓
[3] LLM: classify_event            ← single shot, no tools
       (category, intensity, sentiment, regions, sectors)
     ↓
[4] LLM: extract_tickers           ← single shot
       (which companies mentioned/implied)
     ↓
[5] compute_exposure_map           ← deterministic, DB lookup
     ↓
[6] persist_event_record           ← deterministic, geo_event + event_exposure
     ↓
[7] LLM: embed_event               ← embedding call, persist to pgvector
     ↓
[8] find_historical_analogies      ← deterministic, pgvector query
     ↓
[9] LLM: generate_alert_text       ← single shot, ~80 word summary
     ↓
[10] evaluate_alert_rules          ← deterministic
     ↓
        ┌─ matches rule → [11] dispatch_alert (email/push)
        └─ no match    → [12] log_silent
     ↓
[13] enqueue_deep_dive             ← deterministic, schedule Mode B workflow
```

### Why this is not agentic

Each LLM call:
- Has a fixed, narrow purpose
- Takes structured input
- Returns structured output
- Has no access to tools
- Cannot decide to do something else
- Has bounded token usage

The "intelligence" is in the structured pipeline, not in the model's decisions. This is by design: predictability is paramount in the alert path.

### LLM calls in the Reactive Pipeline

| Step | Purpose | Model | Tokens | Latency target |
|---|---|---|---|---|
| classify_event | Categorize the event | Claude Haiku 4.5 | 2k in / 200 out | < 5s |
| extract_tickers | Find affected companies | Claude Haiku 4.5 | 1k in / 100 out | < 3s |
| embed_event | Vectorize for analogies | OpenAI text-embedding | 500 in | < 2s |
| generate_alert_text | Write the alert | Claude Sonnet 4.6 | 3k in / 200 out | < 8s |

**Total budget:** ~30 seconds of LLM time + ~30 seconds of deterministic operations = under 60 seconds for the full pipeline. Comfortable within the 90-second SLA.

### The handoff to Mode B

Step 13 — `enqueue_deep_dive` — is the publisher pattern. Every event that triggered an alert (and some that didn't, if they're notable) is enqueued for the Event Deep-Dive workflow (Section 11, Workflow 5).

```python
# Step 13
if event.intensity >= 4 or event.matched_portfolio_company:
    workflow_queue.enqueue(
        workflow_type="event_deep_dive",
        inputs={"event_id": event.event_id},
        priority="high",
        scheduled_for=now() + timedelta(minutes=2),  # let market react first
    )
```

The user gets:
- **Within 90 seconds:** Push alert with 80-word summary
- **Within ~10 minutes:** Deep-dive memo (rich analysis, recommendations, scenarios)

This two-stage delivery resolves the latency-vs-quality tradeoff cleanly: fast notification, slow analysis, both arriving in time to inform decisions.

### Observability for the Reactive Pipeline

Same Langfuse stack as Mode B. Every event traced. Every LLM call logged. The Tier 3 evaluation (ex-post calibration) applies equally — did the classifier get the category right? Did the ticker extractor miss anyone? These are measurable from outcome data.

The Reactive Pipeline writes to episodic memory just like Mode B. So when the Event Deep-Dive Agent runs minutes later, it sees the full Reactive Pipeline trace as context.

---

## Section 13 — Cost & Latency Budgets

*Explicit limits, enforced at runtime*

Cost predictability was #2 in your priority ranking, behind quality. The way we deliver predictability is explicit budgets at three levels: per agent, per workflow, per user/day.

### Per-agent budgets

Defined in the agent YAML, enforced by the agent runtime:

```yaml
# In each agent's definition
limits:
  max_input_tokens: 8000
  max_output_tokens: 2000
  max_iterations: 3
  timeout_seconds: 60
  cost_ceiling_usd: 0.30
```

Exceeding any bound fails the agent invocation. The workflow's `evaluate_quality` node sees this and routes the workflow to HIL with a "agent budget exceeded" reason.

### Per-workflow budgets

Total budget across all nodes in a workflow:

```yaml
# In each workflow's YAML
cost_ceiling_usd: 2.50      # hard ceiling
soft_warning_usd: 2.00       # log warning
latency_target_seconds: 300  # 5 min
latency_max_seconds: 600     # 10 min
```

If a workflow approaches the ceiling, subsequent agents get reduced budgets. If the ceiling is hit, the workflow stops, routes to HIL.

### Per-user/day budgets

Aggregate budget for a tenant across all workflows:

```yaml
# In tenant config
daily_budget_usd: 10.00          # MVP single-user (you)
daily_budget_usd: 5.00           # commercial subscription tier
daily_alert_threshold_pct: 80    # alert at 80% of budget
daily_hard_stop_pct: 100         # block new workflows
```

When the threshold is hit, the user gets a UI notification: "Today's analysis budget is 80% used. Want to continue?" When the hard stop is hit, scheduled workflows queue for tomorrow.

### Realistic cost projections

**MVP (single user, you):**
- 1 Morning Brief/day × $1.80 = $54/month
- 1 Watchlist Scan/day × $1.00 = $30/month
- 5 On-Demand Analyses/week × $1.20 = $24/month
- ~10 Event Deep-Dives/week × $2.00 = $80/month
- ~3 Earnings Briefs/week × $1.50 = $18/month
- Tier 1 evaluation overhead: ~15% on top = +$30/month
- Reactive Pipeline: ~$15/month (cheap models, fixed cost per event)

**MVP total: ~$251/month for AI work.** This is roughly consistent with the $45 figure in the Master Architecture, given that the Master estimate excluded Mode B workflows (which we hadn't designed yet) and Tier 1 evaluation overhead. Updated MVP total in `STOCKIQ.md` becomes ~$430/month (data + AI + infra). Still very acceptable for a single-user MVP.

**Growth phase (50 users):**
- Per-user costs scale roughly linearly: ~$5/user/month for AI = $250/month
- Plus shared infrastructure costs (Langfuse, evaluators run only once per workflow type)
- Estimated: ~$400-500/month AI total for 50 users

### Latency budgets

| Workflow | Target | Hard Limit | Notes |
|---|---|---|---|
| Morning Brief | 4 min | 10 min | Runs at 05:30, send target 06:00 |
| On-Demand Analysis | 3 min | 6 min | User waits with progress UI |
| Watchlist Scan | 3 min | 8 min | Runs at 17:30, send target 18:00 |
| Earnings Risk Brief | 4 min | 10 min | Runs at 17:30, send target 18:00 |
| Event Deep-Dive | 7 min | 15 min | Triggered async, no user waiting |
| Reactive Pipeline | 60s | 90s | The SLA |

Latency overruns trigger Langfuse warnings. Three consecutive overruns of the same workflow type triggers an incident review.

---

## Section 14 — Integration with Master Architecture

*Where this layer plugs into system_description.md*

This document and the Master Architecture (system_description.md) describe one system. Here is how the agentic layer slots into the master architecture's modules.

### Module mapping

Recalling the Master Architecture's modules (system_description.md Section 03):

| Master module | Agentic layer's relationship |
|---|---|
| `data_providers` | Unchanged. Provides raw data to ingestion. |
| `ingestion` | Unchanged. Local-first cache-or-fetch. |
| `storage` | Extended with agentic-layer tables (workflow_run, agent_invocation, tool_call, semantic_fact, procedural_pattern, user_feedback). |
| `markets` | Unchanged. Market abstraction. |
| `scoring` | Unchanged. Used by tools and agents but not modified. |
| `events` | Extended. The Reactive Pipeline (Section 12) lives here. Event classification, ticker extraction, exposure mapping. |
| `ai` | Substantially expanded. This is now the home of: Agent Registry, Tool Library, Memory Subsystem, LangGraph workflows. |
| `historical` | Unchanged. Pattern matching, pgvector semantic search. |
| `alerts` | Unchanged. Triggered by Reactive Pipeline. |
| `api` | Extended. New endpoints for: HIL queue UI, on-demand workflow trigger, Q&A interface. |

### New top-level concerns

Three things didn't exist in the Master Architecture and are introduced here:

1. **Observability infrastructure (Langfuse).** New service in docker-compose. New container deployment in Azure.
2. **Workflow runtime (LangGraph).** Long-running workflow execution with checkpointing. Runs in the Celery worker tier from the Master Architecture.
3. **HIL Review UI.** A new section of the web frontend with its own routes.

### Updated technology stack

Adding to the Master Architecture's stack:

| Component | Technology | Purpose |
|---|---|---|
| Workflow orchestration | LangGraph | Mode B workflow graphs |
| Observability | Langfuse (self-hosted) | LLM-level tracing, prompts, evals |
| Observability storage | Clickhouse | Langfuse's analytics backend |
| Prompt management | Git + Langfuse | Source of truth + runtime |
| Evaluation | Langfuse Evaluators + custom | Tier 1, 2, 3 |

### Updated deployment topology

The Master Architecture's hybrid deployment topology (system_description.md Section 15) gains:

```
Local layer (kept identical from Master Architecture):
- PostgreSQL + TimescaleDB
- pgvector
- Redis
+ Workflow checkpointing tables (in PostgreSQL)
+ Episodic/semantic/procedural memory tables (in PostgreSQL)

New: Observability layer (lives locally or in Azure, your choice):
- Langfuse server
- Langfuse PostgreSQL
- Clickhouse for analytics

Cloud layer (kept identical from Master Architecture):
- Azure OpenAI (event classification, embeddings)
- Container Apps (API + workers)
- Claude API (recommendation/synthesis agents)
+ Workflow execution happens in Container Apps workers, not a new tier
```

### Costs updated

Adding agentic layer to the Master Architecture's cost model:

**MVP phase:**
- Master Architecture original MVP: ~$268/month
- Add Langfuse self-hosted infrastructure: ~$20/month (containers + storage)
- Add Mode B workflow AI costs: ~$200/month (the dominant new cost)
- Add Tier 1 evaluation overhead: ~$30/month
- **Updated MVP total: ~$520/month**

This is still cleanly within "self-financing at a $30/user subscription with 20 users" territory, and an order of magnitude below institutional alternatives.

### Roadmap implications

The Master Architecture's 6-phase roadmap (system_description.md Section 17) gets refined:

- **Phase 1-3** (foundation, scoring, map) unchanged.
- **Phase 4** (AI + Alerts) becomes the agentic layer build:
  - Tool Library implementation
  - First 3 agent roles (Relevance, Historical Context, Synthesizer)
  - Morning Brief workflow as the first complete Mode B workflow
  - Langfuse stood up with Tier 3 ex-post calibration from day 1
  - Tier 1 LLM-as-judge added 2 weeks in
  - Tier 2 golden dataset bootstrapped over month 6
- **Phase 5** (Time Machine + Polish) gains:
  - All 9 agent roles implemented
  - All 5 workflows operational
  - Memory subsystem layers 2 (semantic) and 3 (procedural) activated
  - HIL queue UI shipped
- **Phase 6** (new markets) unchanged.

---

## Closing Note

This document describes an agentic architecture that prioritizes quality of reasoning, cost predictability, and observability over agent autonomy. It treats agents as named analysts with personas and scoped tools, not as autonomous explorers. It builds a four-layer memory subsystem from day 1 because the learning loop is the differentiator. It enforces quality through human-in-the-loop review and three tiers of evaluation, including the unique-to-StokAI ex-post calibration against actual market outcomes.

The architecture is opinionated and deliberate. Every choice traces back to the master architecture's principles and the design partner's stated priorities. There is no magic, no autonomous self-improvement, no agentic mystique. Just structured intelligence flowing through observable graphs, with humans in the loop at the points where judgment matters most.

This is the system that delivers the 90-seconds-vs-40-minutes promise. Not because the agents are smart in isolation, but because the architecture makes their work compoundable, observable, and improvable.

---

*StokAI AGENTIC ARCHITECTURE · v1.0 · May 2026*
*Companion to system_description.md · Ready for implementation*
