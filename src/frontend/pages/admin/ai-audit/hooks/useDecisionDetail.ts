/**
 * hooks/useDecisionDetail — TanStack Query hook for single AI decision detail.
 *
 * PLAN-F-029 TASK-012
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import type { AIDecisionDetail } from '../DecisionDetailDrawer';

export function useDecisionDetail(decisionId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'audit', 'decision', decisionId],
    queryFn: () => api<AIDecisionDetail>('/admin/audit/decisions/' + decisionId),
    enabled: Boolean(decisionId) && enabled,
  });
}
