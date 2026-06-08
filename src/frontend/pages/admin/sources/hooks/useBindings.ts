/**
 * useBindings — TanStack Query hooks for market-source binding management.
 *
 * Wraps:
 *   GET    /api/v1/admin/bindings
 *   PUT    /api/v1/admin/bindings
 *   DELETE /api/v1/admin/bindings
 *
 * PLAN-F-028 TASK-010
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export interface Binding {
  market_id: string;
  interface_type: string;
  source_id: string;
  role: string;
}

export const BINDINGS_QUERY_KEY = ["admin", "bindings"] as const;

// ── Fetch ─────────────────────────────────────────────────────────────────────

async function fetchBindings(): Promise<Binding[]> {
  return api<Binding[]>("/v1/admin/bindings");
}

export function useBindings() {
  return useQuery<Binding[], Error>({
    queryKey: BINDINGS_QUERY_KEY,
    queryFn: fetchBindings,
    staleTime: 30_000,
  });
}

// ── Upsert ────────────────────────────────────────────────────────────────────

export interface UpsertBindingVars {
  market_id: string;
  interface_type: string;
  source_id: string;
  role: string;
}

async function upsertBinding(vars: UpsertBindingVars): Promise<Binding> {
  return api<Binding>("/v1/admin/bindings", {
    method: "PUT",
    body: JSON.stringify(vars),
  });
}

export function useUpsertBinding() {
  const queryClient = useQueryClient();
  return useMutation<Binding, Error, UpsertBindingVars>({
    mutationFn: upsertBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: BINDINGS_QUERY_KEY });
    },
  });
}

// ── Delete ────────────────────────────────────────────────────────────────────

export interface DeleteBindingVars {
  market_id: string;
  interface_type: string;
  source_id: string;
}

async function deleteBinding(vars: DeleteBindingVars): Promise<void> {
  await api<void>("/v1/admin/bindings", {
    method: "DELETE",
    body: JSON.stringify(vars),
  });
}

export function useDeleteBinding() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, DeleteBindingVars>({
    mutationFn: deleteBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: BINDINGS_QUERY_KEY });
    },
  });
}
