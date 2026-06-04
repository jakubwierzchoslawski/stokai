/**
 * useRecommendationTrackRecord — TanStack Query hook for fetching recommendation
 * track record from the compliance API.
 *
 * GET /api/v1/compliance/track-record/{companyId}?limit={limit}
 *
 * Cache key: ["track-record", companyId]
 * Stale time: 5 minutes
 *
 * PLAN-N-012 TASK-005
 */
import { useQuery } from '@tanstack/react-query';

export interface TrackRecordEntry {
  rec_id: string;
  company_ticker: string;
  action_signal: string;
  confidence: number;
  sample_size: number;
  generated_at: string;
  actual_t1d: number | null;
  actual_t1w: number | null;
  accuracy: number | null;
  disclaimer_required: boolean;
}

export interface TrackRecordResponse {
  company_id: string;
  company_ticker: string;
  entries: TrackRecordEntry[];
  total: number;
  direction_correct_t1d_pct: number | null;
  direction_correct_t1w_pct: number | null;
}

const TRACK_RECORD_STALE_MS = 5 * 60 * 1000; // 5 minutes

async function fetchTrackRecord(
  companyId: string,
  limit: number,
): Promise<TrackRecordResponse> {
  const url = `/api/v1/compliance/track-record/${companyId}?limit=${limit}`;
  const resp = await fetch(url, { credentials: 'include' });

  if (!resp.ok) {
    throw new Error(`Failed to fetch track record: ${resp.status}`);
  }

  return resp.json() as Promise<TrackRecordResponse>;
}

export function trackRecordQueryKey(companyId: string): readonly [string, string] {
  return ['track-record', companyId] as const;
}

export interface UseRecommendationTrackRecordOptions {
  companyId: string;
  limit?: number;
}

export function useRecommendationTrackRecord({
  companyId,
  limit = 50,
}: UseRecommendationTrackRecordOptions) {
  return useQuery({
    queryKey: trackRecordQueryKey(companyId),
    queryFn: () => fetchTrackRecord(companyId, limit),
    staleTime: TRACK_RECORD_STALE_MS,
    enabled: !!companyId,
  });
}
