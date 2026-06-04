/**
 * hooks/usePromptHistory — TanStack Query hook for prompt version history.
 *
 * Fetches GET /api/v1/admin/audit/prompts/{agent_role}/history.
 *
 * PLAN-F-029 TASK-009
 */
import { useQuery } from '@tanstack/react-query';

export interface PromptVersionEntry {
  version_id: string;
  agent_role: string;
  label_applied: string;
  published_at: string;
  rolled_back_at: string | null;
  quality_metrics: Record<string, number> | null;
}

async function fetchPromptHistory(
  agentRole: string,
  limit = 50
): Promise<PromptVersionEntry[]> {
  const res = await fetch(
    `/api/v1/admin/audit/prompts/${encodeURIComponent(agentRole)}/history?limit=${limit}`
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  return json.data;
}

export function usePromptHistory(agentRole: string, limit = 50) {
  return useQuery({
    queryKey: ['admin', 'audit', 'prompts', agentRole, 'history', limit] as const,
    queryFn: () => fetchPromptHistory(agentRole, limit),
    enabled: Boolean(agentRole),
  });
}

export const PROMPT_HISTORY_QUERY_KEY = (role: string) =>
  ['admin', 'audit', 'prompts', role, 'history'] as const;
