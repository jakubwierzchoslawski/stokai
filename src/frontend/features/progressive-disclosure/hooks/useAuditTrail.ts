/**
 * useAuditTrail — TanStack Query hook for GET /api/v1/events/{id}/audit-trail.
 *
 * PLAN-F-020 TASK-005
 *
 * Lazy — fires only when the user opens "Why this read?" (enabled=true).
 * No staleTime — audit trail data is immutable (reasoning chain never changes).
 */
import { useQuery, UseQueryResult } from '@tanstack/react-query';

import { fetchAuditTrail } from '../api/disclosure.api';
import type { AuditTrailData } from '../types/disclosure.types';

export function useAuditTrail(
  eventId: string | null,
  enabled: boolean,
): UseQueryResult<AuditTrailData, Error> {
  return useQuery<AuditTrailData, Error>({
    queryKey: ['audit-trail', eventId],
    queryFn: () => fetchAuditTrail(eventId!),
    enabled: !!eventId && enabled,
    // No staleTime — audit trail is immutable
  });
}
