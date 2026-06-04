/**
 * disclosure.types.ts — TypeScript interfaces for the Progressive Disclosure UI.
 *
 * PLAN-F-020 TASK-001
 *
 * Covers all three disclosure levels:
 *   Level 1 — PopupData (EventPopup)
 *   Level 2 — SidePanelData (SidePanel)
 *   Level 3 — AuditTrailData (AuditTrailView) + DeepDiveData (DeepDivePage)
 */

// ── Shared primitives ─────────────────────────────────────────────────────────

export interface TickerDelta {
  ticker: string;
  /** Positive or negative float */
  score_delta: number;
}

export interface SparklinePoint {
  /** ISO date string */
  ts: string;
  close: number;
}

export interface AnalogSummary {
  /** UUID of the historical reference event */
  event_id: string;
  headline: string;
  /** ISO date string */
  occurred_at: string;
  /** 0–1 */
  similarity_score: number;
}

export interface AffectedCompany {
  /** UUID */
  company_id: string;
  ticker: string;
  name: string;
  /** Current geo-adjusted score (0–100) */
  score: number;
  /** score_new - score_previous */
  delta: number;
}

export interface SocialPost {
  post_id: string;
  source: string;
  text: string;
  /** ISO timestamp */
  timestamp: string;
}

// ── Level 1: Popup ────────────────────────────────────────────────────────────

export interface PopupData {
  /** UUID */
  event_id: string;
  category: string[];
  /** 1–5 */
  intensity: number;
  headline: string;
  /** Human-readable relative time: "14 minutes ago" */
  time_ago: string;
  location: string;
  exposed_holdings_count: number;
  tickers_with_delta: TickerDelta[];
  /** HOLD | WATCH | BUY_OPP | REDUCE_RISK | HEDGE | CONTRARIAN */
  action_signal: string;
  /** 0–1 */
  confidence: number;
  sample_size: number;
  /** true when sample_size < 5; set at API serialization level */
  low_sample: boolean;
}

// ── Level 2: Side Panel ───────────────────────────────────────────────────────

export interface SidePanelData extends PopupData {
  summary: string;
  sparklines: Array<{ ticker: string; ohlcv_7d: SparklinePoint[] }>;
  rationale: string;
  /** Top 3 historical analogs */
  analogies: AnalogSummary[];
  affected_companies: AffectedCompany[];
  is_contrarian: boolean;
  /** Non-null when is_contrarian=true */
  contrarian_callout: string | null;
  /** Null when social sources are disabled (off by default) */
  social_posts: SocialPost[] | null;
  /** Relative path: /events/{id}/audit-trail */
  audit_trail_url: string;
}

// ── Audit Trail ───────────────────────────────────────────────────────────────

export interface ReasoningStep {
  agent_role: string;
  step_index: number;
  content: string;
  /** Tool names called in this step */
  tool_calls: string[];
}

export interface AuditTrailData {
  /** UUID */
  event_id: string;
  /** Git SHA of the prompt version used */
  prompt_version: string;
  /** Full Langfuse trace URL; empty string when Langfuse is disabled */
  langfuse_trace_url: string;
  analogies: Array<AnalogSummary & { similarity_score: number }>;
  /** Ordered by step_index */
  reasoning_steps: ReasoningStep[];
}

// ── Level 3: Deep Dive ────────────────────────────────────────────────────────

export interface ScenarioNode {
  label: string;
  /** 0–1 */
  probability: number;
  description: string;
  children: ScenarioNode[];
}

export interface DeepDiveData {
  /** UUID */
  event_id: string;
  /** Full analysis prose (may contain markdown headings) */
  memo: string;
  /** Null when no scenario analysis is available */
  scenario_tree: ScenarioNode | null;
  /** Full table (not limited to 3) */
  analogies: AnalogSummary[];
  affected_companies: AffectedCompany[];
  /** ISO timestamp of when this deep dive was generated */
  generated_at: string;
}

// ── Pending status (202 polling) ──────────────────────────────────────────────

export interface DeepDivePending {
  status: 'pending';
}

export type DeepDiveResult = DeepDiveData | DeepDivePending;

export function isDeepDivePending(r: DeepDiveResult): r is DeepDivePending {
  return (r as DeepDivePending).status === 'pending';
}
