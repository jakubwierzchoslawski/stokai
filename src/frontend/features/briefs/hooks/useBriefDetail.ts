/**
 * useBriefDetail — TanStack Query for a single brief detail.
 *
 * Fetches GET /api/v1/briefs/:id.
 *
 * PLAN-F-026 TASK-006
 */
import { useQuery } from '@tanstack/react-query';
import type { BriefDetailResponse } from '../briefs.types';
import { api } from '@/lib/api/client';

async function fetchBriefDetail(briefId: string): Promise<BriefDetailResponse> {
  return api<BriefDetailResponse>('/briefs/' + briefId);
}

export function useBriefDetail(briefId: string) {
  return useQuery({
    queryKey: ['brief', briefId],
    queryFn: () => fetchBriefDetail(briefId),
    enabled: Boolean(briefId),
  });
}
