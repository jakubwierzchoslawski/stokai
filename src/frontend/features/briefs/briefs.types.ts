/**
 * briefs.types.ts — TypeScript types matching the Briefs API response DTOs.
 *
 * PLAN-F-026 TASK-005
 */

export type BriefType =
  | 'morning_brief'
  | 'watchlist_scan'
  | 'earnings_brief'
  | 'event_deep_dive';

export interface BriefListItem {
  brief_id: string;
  type: BriefType;
  date: string | null;
  headline: string;
  confidence: number;
  delivery_status: string;
}

export interface BriefDetail extends BriefListItem {
  sample_size: number;
  low_sample: boolean;
  content_html: string;
}

export interface BriefListResponse {
  data: {
    items: BriefListItem[];
    next_cursor: string | null;
  };
  meta: Record<string, unknown>;
  error: null;
}

export interface BriefDetailResponse {
  data: BriefDetail;
  meta: Record<string, unknown>;
  error: null;
}

export interface FeedbackRequest {
  feedback_type: 'thumbs_up' | 'thumbs_down' | 'edit';
  correction?: string | null;
}

export interface FeedbackResponse {
  data: { feedback_id: string };
  meta: Record<string, unknown>;
  error: null;
}

export const BRIEF_TYPE_LABELS: Record<BriefType, string> = {
  morning_brief: 'Morning Brief',
  watchlist_scan: 'Watchlist Scan',
  earnings_brief: 'Earnings Brief',
  event_deep_dive: 'Event Deep-Dive',
};
