/**
 * useBriefDetail — TanStack Query for a single brief detail.
 *
 * Fetches GET /api/v1/briefs/:id.
 *
 * PLAN-F-026 TASK-006
 */
import { useQuery } from '@tanstack/react-query';
import type { BriefDetailResponse } from '../briefs.types';

async function fetchBriefDetail(briefId: string): Promise<BriefDetailResponse> {
  const resp = await fetch(`/api/v1/briefs/${briefId}`, {
    credentials: 'include',
  });
  if (!resp.ok) {
    throw new Error(`Failed to fetch brief ${briefId}: ${resp.status}`);
  }
  return resp.json() as Promise<BriefDetailResponse>;
}

export function useBriefDetail(briefId: string) {
  return useQuery({
    queryKey: ['brief', briefId],
    queryFn: () => fetchBriefDetail(briefId),
    enabled: Boolean(briefId),
  });
}
