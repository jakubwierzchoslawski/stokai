/**
 * useSidePanelData — TanStack Query hook for GET /api/v1/events/{id}/side-panel.
 *
 * PLAN-F-020 TASK-005
 *
 * Lazy — only fires when the side panel is opened (enabled=true).
 * staleTime: 60_000 — side panel data stays fresh for 60 seconds.
 */
import { useQuery, UseQueryResult } from '@tanstack/react-query';

import { fetchSidePanelData } from '../api/disclosure.api';
import type { SidePanelData } from '../types/disclosure.types';

export function useSidePanelData(
  eventId: string | null,
  enabled: boolean,
): UseQueryResult<SidePanelData, Error> {
  return useQuery<SidePanelData, Error>({
    queryKey: ['side-panel', eventId],
    queryFn: () => fetchSidePanelData(eventId!),
    enabled: !!eventId && enabled,
    staleTime: 60_000,
  });
}
