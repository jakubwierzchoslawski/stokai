/**
 * useScoreHistory — TanStack Query hook for fetching OHLCV price history.
 *
 * GET /api/v1/companies/{companyId}/prices?interval={interval}&from_days={fromDays}
 * staleTime: 60 seconds
 *
 * PLAN-F-023 TASK-005
 */
import { useQuery } from '@tanstack/react-query';
import type { PriceBar } from '../types';

const SCORE_HISTORY_STALE_MS = 60_000;

async function fetchPriceHistory(
  companyId: string,
  interval: string,
  fromDays: number,
): Promise<PriceBar[]> {
  const params = new URLSearchParams({
    interval,
    price_from_days: String(fromDays),
  });

  const url = `/api/v1/companies/${companyId}/prices?${params.toString()}`;
  const resp = await fetch(url, { credentials: 'include' });

  if (!resp.ok) {
    throw new Error(`Failed to fetch price history: ${resp.status}`);
  }

  return resp.json() as Promise<PriceBar[]>;
}

export function scoreHistoryQueryKey(companyId: string, interval: string, fromDays: number) {
  return ['priceHistory', companyId, interval, fromDays] as const;
}

export interface UseScoreHistoryOptions {
  companyId: string;
  interval?: string;
  fromDays?: number;
}

export function useScoreHistory({
  companyId,
  interval = '1d',
  fromDays = 90,
}: UseScoreHistoryOptions) {
  return useQuery({
    queryKey: scoreHistoryQueryKey(companyId, interval, fromDays),
    queryFn: () => fetchPriceHistory(companyId, interval, fromDays),
    staleTime: SCORE_HISTORY_STALE_MS,
    enabled: !!companyId,
  });
}
