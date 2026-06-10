/**
 * hooks/useWorkflowHistory — TanStack Query hook for workflow history panel.
 *
 * Cursor-based pagination. Re-run mutation included.
 *
 * PLAN-F-029 TASK-011
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import { api } from '@/lib/api/client';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ToolCallSummary {
  tool_call_id: string;
  tool_name: string;
  duration_ms: number;
  cost_tier: string | null;
  cached: boolean;
}

export interface AgentInvocationSummary {
  invocation_id: string;
  agent_role_id: string;
  model_used: string;
  prompt_version: string;
  confidence: number | null;
  cost_usd: number;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls: ToolCallSummary[];
}

export interface WorkflowRunSummary {
  workflow_id: string;
  workflow_type: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  cost_usd: number;
  langfuse_trace_id: string | null;
}

export interface WorkflowRunDetail extends WorkflowRunSummary {
  agent_invocations: AgentInvocationSummary[];
  final_state: Record<string, unknown> | null;
}

export interface RerunResponse {
  new_workflow_id: string;
  workflow_type: string;
  dispatched_at: string;
}

// ── API ────────────────────────────────────────────────────────────────────────

async function fetchWorkflows(
  cursor: string | null,
  limit: number
): Promise<{ data: WorkflowRunSummary[]; next_cursor: string | null }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  return api('/admin/audit/workflows?' + params.toString());
}

async function postRerun(workflowId: string): Promise<RerunResponse> {
  return api<RerunResponse>(
    '/admin/audit/workflows/' + workflowId + '/rerun',
    { method: 'POST' },
  );
}

// ── useWorkflowHistory hook ────────────────────────────────────────────────────

export function useWorkflowHistory(limit = 50) {
  const [cursor, setCursor] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['admin', 'audit', 'workflows', cursor, limit] as const,
    queryFn: () => fetchWorkflows(cursor, limit),
    placeholderData: (prev) => prev,
  });

  const loadNextPage = useCallback(() => {
    if (query.data?.next_cursor) {
      setCursor(query.data.next_cursor);
    }
  }, [query.data?.next_cursor]);

  return {
    runs: query.data?.data ?? [],
    nextCursor: query.data?.next_cursor ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    loadNextPage,
    refetch: query.refetch,
  };
}

// ── useRerunWorkflow mutation ──────────────────────────────────────────────────

export function useRerunWorkflow() {
  const queryClient = useQueryClient();

  return useMutation<RerunResponse, Error, string>({
    mutationFn: postRerun,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'audit', 'workflows'] });
    },
  });
}

export const WORKFLOW_HISTORY_QUERY_KEY = ['admin', 'audit', 'workflows'] as const;
