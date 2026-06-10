/**
 * hooks/useWorkflowDetail — TanStack Query hook for single workflow run detail.
 *
 * PLAN-F-029 TASK-012
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import type { WorkflowRunDetail } from './useWorkflowHistory';

export function useWorkflowDetail(workflowId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'audit', 'workflow', workflowId],
    queryFn: () => api<WorkflowRunDetail>('/admin/audit/workflows/' + workflowId),
    enabled: Boolean(workflowId) && enabled,
  });
}
