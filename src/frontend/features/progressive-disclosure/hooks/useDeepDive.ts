/**
 * useDeepDive — TanStack Query hook for GET /api/v1/events/{id}/deep-dive.
 *
 * PLAN-F-020 TASK-005
 *
 * Lazy — fires only when enabled=true (side panel "Full Analysis" button).
 * Handles 202 "pending" response by polling every 5 seconds.
 * Stops polling after 85 attempts (85 × 5s ≈ 7 minutes) to prevent indefinite loops.
 */
import { useQuery, UseQueryResult } from '@tanstack/react-query';

import { fetchDeepDive } from '../api/disclosure.api';
import type { DeepDiveResult } from '../types/disclosure.types';
import { isDeepDivePending } from '../types/disclosure.types';

const MAX_POLL_ATTEMPTS = 85;
const POLL_INTERVAL_MS = 5_000;

export function useDeepDive(
  eventId: string | null,
  enabled: boolean,
): UseQueryResult<DeepDiveResult, Error> & { pollCount: number } {
  const result = useQuery<DeepDiveResult, Error>({
    queryKey: ['deep-dive', eventId],
    queryFn: () => fetchDeepDive(eventId!),
    enabled: !!eventId && enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      if (!isDeepDivePending(data)) return false;

      // Extract current refetch count from fetchMeta if available
      const fetchCount = (query.state as { dataUpdateCount?: number }).dataUpdateCount ?? 0;
      if (fetchCount >= MAX_POLL_ATTEMPTS) return false;

      return POLL_INTERVAL_MS;
    },
  });

  return {
    ...result,
    pollCount: (result as unknown as { fetchCount?: number }).fetchCount ?? 0,
  };
}
