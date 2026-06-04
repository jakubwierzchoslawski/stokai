/**
 * useSources — TanStack Query hook for fetching all admin data sources.
 *
 * Wraps GET /api/v1/admin/sources. Returns source list with embedded health stats.
 * useToggleSource mutation calls PATCH .../enable with optimistic UI (reverts on error).
 *
 * PLAN-F-028 TASK-007
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export interface HealthStats {
  calls_today: number;
  errors_today: number;
  rate_limit_pct_used: number;
  estimated_cost_today: number;
}

export interface SourceConfig {
  source_id: string;
  display_name: string;
  interface_type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  cost_tier: string;
  priority: number;
  health: HealthStats | null;
}

interface ApiEnvelope<T> {
  data: T;
  error: { code: string; message: string } | null;
}

async function fetchSources(): Promise<SourceConfig[]> {
  const response = await fetch("/api/v1/admin/sources", {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch sources: ${response.status}`);
  }
  const envelope: ApiEnvelope<SourceConfig[]> = await response.json();
  if (envelope.error) {
    throw new Error(envelope.error.message);
  }
  return envelope.data;
}

async function patchEnabled(sourceId: string, enabled: boolean): Promise<SourceConfig> {
  const response = await fetch(`/api/v1/admin/sources/${sourceId}/enable`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) {
    throw new Error(`Failed to toggle source: ${response.status}`);
  }
  const envelope: ApiEnvelope<SourceConfig> = await response.json();
  if (envelope.error) {
    throw new Error(envelope.error.message);
  }
  return envelope.data;
}

/** React Query key for sources list. */
export const SOURCES_QUERY_KEY = ["admin", "sources"] as const;

/** Fetch and cache all data sources. */
export function useSources() {
  return useQuery<SourceConfig[], Error>({
    queryKey: SOURCES_QUERY_KEY,
    queryFn: fetchSources,
    staleTime: 30_000,
  });
}

export interface ToggleSourceVars {
  sourceId: string;
  enabled: boolean;
}

/**
 * Mutation to toggle source enabled state.
 * Uses optimistic UI: updates the cache immediately, reverts on error.
 */
export function useToggleSource(options?: { onError?: (err: Error) => void }) {
  const queryClient = useQueryClient();

  return useMutation<SourceConfig, Error, ToggleSourceVars>({
    mutationFn: ({ sourceId, enabled }) => patchEnabled(sourceId, enabled),

    onMutate: async ({ sourceId, enabled }) => {
      // Cancel in-flight queries to avoid race conditions
      await queryClient.cancelQueries({ queryKey: SOURCES_QUERY_KEY });

      // Snapshot previous value for rollback
      const previous = queryClient.getQueryData<SourceConfig[]>(SOURCES_QUERY_KEY);

      // Optimistically update cache
      queryClient.setQueryData<SourceConfig[]>(SOURCES_QUERY_KEY, (old) =>
        old
          ? old.map((s) => (s.source_id === sourceId ? { ...s, enabled } : s))
          : old
      );

      return { previous };
    },

    onError: (_err, _vars, context: any) => {
      // Rollback to previous snapshot
      if (context?.previous !== undefined) {
        queryClient.setQueryData(SOURCES_QUERY_KEY, context.previous);
      }
      options?.onError?.(_err);
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SOURCES_QUERY_KEY });
    },
  });
}
