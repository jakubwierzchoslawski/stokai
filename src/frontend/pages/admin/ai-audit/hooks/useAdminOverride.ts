/**
 * hooks/useAdminOverride — TanStack Query mutation for admin override.
 *
 * POSTs to POST /api/v1/admin/audit/decisions/{decision_id}/override.
 * On success, invalidates the decision log query.
 *
 * PLAN-F-029 TASK-008
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { DECISION_LOG_QUERY_KEY } from './useDecisionLog';

export interface AdminOverrideRequest {
  decision_id: string;
  corrected_output: string;
  override_reason: string;
}

export interface AdminOverrideResponse {
  decision_id: string;
  feedback_id: string;
  golden_dataset_candidate_id: string;
  proposed_prompt_adjustment: string;
  status: string;
}

async function postAdminOverride(
  request: AdminOverrideRequest
): Promise<AdminOverrideResponse> {
  const res = await fetch(
    `/api/v1/admin/audit/decisions/${request.decision_id}/override`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message =
      body?.error?.message ?? `Override failed with HTTP ${res.status}`;
    throw new Error(message);
  }
  const json = await res.json();
  return json.data;
}

export function useAdminOverride() {
  const queryClient = useQueryClient();

  return useMutation<AdminOverrideResponse, Error, AdminOverrideRequest>({
    mutationFn: postAdminOverride,
    onSuccess: () => {
      // Invalidate decision log to reflect the override
      queryClient.invalidateQueries({ queryKey: DECISION_LOG_QUERY_KEY });
    },
  });
}
