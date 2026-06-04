/**
 * types.ts — TypeScript interfaces for the Company Detail screen.
 *
 * PLAN-F-023 TASK-005
 */

export interface FundamentalsPanel {
  pe_ratio: number | null;
  eps: number | null;
  revenue: number | null;
  debt_to_equity: number | null;
  source: string;
  as_of: string;
}

export interface ScoreBreakdownItem {
  indicator_id: string;
  indicator_name: string;
  formula_summary: string;
  weight: number;
  raw_value: number | null;
  score: number;
  geo_adjusted: number | null;
  sub_score_contribution: number;
  sparkline: number[];
}

export interface ActiveEventSummary {
  event_id: string;
  title: string;
  occurred_at: string;
  intensity: number;
  category: string[];
  exposure_magnitude: number;
}

export interface AnalysisHistoryItem {
  rec_id: string;
  generated_at: string;
  workflow_type: string;
  action_signal: string;
  confidence: number;
  rationale_summary: string;
}

export interface TrackRecordItem {
  rec_id: string;
  generated_at: string;
  action_signal: string;
  direction: string;
  confidence: number;
  actual_t1d: number | null;
  actual_t1w: number | null;
  correct_t1d: boolean | null;
  correct_t1w: boolean | null;
}

export interface PriceBar {
  company_id: string;
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  interval: string;
}

export interface CompanyDetailResponse {
  company_id: string;
  ticker: string;
  name: string;
  sector: string;
  market_cap: number | null;
  fundamentals: FundamentalsPanel;
  scores: ScoreBreakdownItem[];
  active_events: ActiveEventSummary[];
  analysis_history: AnalysisHistoryItem[];
  track_record: TrackRecordItem[];
  directional_accuracy_t1d: number | null;
}
