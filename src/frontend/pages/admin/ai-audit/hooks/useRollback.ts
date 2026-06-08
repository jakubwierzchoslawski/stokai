/**
 * hooks/useRollback — TanStack Query mutation for prompt rollback.
 *
 * POSTs to POST /api/v1/admin/audit/prompts/{agent_role}/rollback.
 *
 * PLAN-F-029 TASK-009
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { PROMPT_HISTORY_QUERY_KEY } from './usePromptHistory';

export interface RollbackRequest {
  agent_role: string;
  to_version: string;
}

export interface RollbackResponse {
  agent_role: string;
  previous_version: string;
  rolled_back_to: string;
  effective_at: string;
}

async function postRollback(request: RollbackRequest): Promise<RollbackResponse> {
  const res = await fetch(
    `/api/v1/admin/audit/prompts/${encodeURIComponent(request.agent_role)}/rollback`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `Rollback failed with HTTP ${res.status}`);
  }
  const json = await res.json();
  return json.data;
}

export function useRollback() {
  const queryClient = useQueryClient();

  return useMutation<RollbackResponse, Error, RollbackRequest>({
    mutationFn: postRollback,
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: PROMPT_HISTORY_QUERY_KEY(data.agent_role),
      });
    },
  });
}
