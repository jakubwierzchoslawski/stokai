/**
 * useScoreAtTime.ts — TanStack Query hook for score-at-time data.
 *
 * When enabled=false, returns { scores: {}, isLoading: false } immediately.
 * When enabled=true, calls GET /api/v1/scores/history?company_ids=&at= and
 * transforms the ScoreAtTime[] response into Record<company_id, ScoreAtTime>
 * for O(1) lookup by the score overlay.
 *
 * Query key includes sorted company IDs + at timestamp for correct caching.
 *
 * PLAN-F-021 TASK-006
 */

import { useQuery } from '@tanstack/react-query';
import type { ScoreAtTime } from '../types/time-mode.types';

// ── Parameters ────────────────────────────────────────────────────────────────

export interface ScoreAtTimeParams {
  companyIds: string[];
  /** ISO 8601 datetime; closest snapshot at or before this time is returned. */
  at: string;
  enabled: boolean;
}

// ── Result ────────────────────────────────────────────────────────────────────

export interface UseScoreAtTimeResult {
  /** Keyed by company_id for O(1) lookup. */
  scores: Record<string, ScoreAtTime>;
  isLoading: boolean;
}

// ── Token accessor ────────────────────────────────────────────────────────────

function getAuthToken(): string {
  try {
    return (
      localStorage.getItem('auth_token') ??
      localStorage.getItem('access_token') ??
      ''
    );
  } catch {
    return '';
  }
}

// ── Fetch function ────────────────────────────────────────────────────────────

async function fetchScoresAtTime(
  companyIds: string[],
  at: string,
): Promise<Record<string, ScoreAtTime>> {
  const url = new URL('/api/v1/scores/history', window.location.origin);
  // Deduplicate and send as CSV; sort for cache-key consistency.
  const deduped = [...new Set(companyIds)].sort();
  url.searchParams.set('company_ids', deduped.join(','));
  url.searchParams.set('at', at);

  const token = getAuthToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(url.toString(), { headers, credentials: 'include' });
  if (!response.ok) {
    throw new Error(`GET /api/v1/scores/history returned HTTP ${response.status}`);
  }

  const body: unknown = await response.json();
  const payload =
    body !== null && typeof body === 'object' && 'data' in (body as Record<string, unknown>)
      ? (body as Record<string, unknown>)['data']
      : body;

  if (!Array.isArray(payload)) {
    throw new Error('Scores-at-time response is not an array');
  }

  // Transform array → Record<company_id, ScoreAtTime>.
  const map: Record<string, ScoreAtTime> = {};
  for (const item of payload as ScoreAtTime[]) {
    if (item.company_id) {
      map[item.company_id] = item;
    }
  }
  return map;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useScoreAtTime(params: ScoreAtTimeParams): UseScoreAtTimeResult {
  const { companyIds, at, enabled } = params;

  // Sort for stable cache key.
  const sortedIds = [...companyIds].sort();

  const queryResult = useQuery<Record<string, ScoreAtTime>, Error>({
    queryKey: ['scores-at-time', sortedIds.join(','), at],
    queryFn: () => fetchScoresAtTime(sortedIds, at),
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  if (!enabled) {
    return { scores: {}, isLoading: false };
  }

  return {
    scores: queryResult.data ?? {},
    isLoading: queryResult.isLoading,
  };
}
