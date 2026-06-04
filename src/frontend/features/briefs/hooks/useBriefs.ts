/**
 * useBriefs — TanStack Query infinite query for the briefs list.
 *
 * Fetches GET /api/v1/briefs with optional type filter and cursor pagination.
 *
 * PLAN-F-026 TASK-005
 */
import { useInfiniteQuery } from '@tanstack/react-query';
import type { BriefListResponse, BriefType } from '../briefs.types';

interface UseBriefsOptions {
  briefType?: BriefType | null;
}

async function fetchBriefs(
  briefType: BriefType | null | undefined,
  cursor: string | null,
): Promise<BriefListResponse> {
  const params = new URLSearchParams();
  if (briefType) params.set('type', briefType);
  if (cursor) params.set('cursor', cursor);
  params.set('limit', '20');

  const resp = await fetch(`/api/v1/briefs?${params.toString()}`, {
    credentials: 'include',
  });
  if (!resp.ok) {
    throw new Error(`Failed to fetch briefs: ${resp.status}`);
  }
  return resp.json() as Promise<BriefListResponse>;
}

export function useBriefs({ briefType }: UseBriefsOptions = {}) {
  return useInfiniteQuery({
    queryKey: ['briefs', briefType ?? null],
    queryFn: ({ pageParam }) =>
      fetchBriefs(briefType, (pageParam as string | null) ?? null),
    getNextPageParam: (lastPage: BriefListResponse) =>
      lastPage.data.next_cursor ?? undefined,
    initialPageParam: null as string | null,
  });
}
