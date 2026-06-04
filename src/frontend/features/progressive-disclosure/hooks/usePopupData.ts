/**
 * usePopupData — TanStack Query hook for GET /api/v1/events/{id}/popup.
 *
 * PLAN-F-020 TASK-005
 *
 * staleTime: 30_000 — popup data stays fresh for 30 seconds, enabling the
 * 300ms render target (REQ-N-001) for recently-seen events from the cache.
 */
import { useQuery, UseQueryResult } from '@tanstack/react-query';

import { fetchPopupData } from '../api/disclosure.api';
import type { PopupData } from '../types/disclosure.types';

export function usePopupData(
  eventId: string | null,
): UseQueryResult<PopupData, Error> {
  return useQuery<PopupData, Error>({
    queryKey: ['popup', eventId],
    queryFn: () => fetchPopupData(eventId!),
    enabled: !!eventId,
    staleTime: 30_000,
  });
}
