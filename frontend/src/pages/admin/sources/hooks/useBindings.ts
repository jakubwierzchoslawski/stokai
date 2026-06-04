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

export interface Binding {
  market_id: string;
  interface_type: string;
  source_id: string;
  role: string;
}

interface ApiEnvelope<T> {
  data: T;
  error: { code: string; message: string } | null;
}

export const BINDINGS_QUERY_KEY = ["admin", "bindings"] as const;

// ── Fetch ─────────────────────────────────────────────────────────────────────

async function fetchBindings(): Promise<Binding[]> {
  const response = await fetch("/api/v1/admin/bindings", {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch bindings: ${response.status}`);
  }
  const envelope: ApiEnvelope<Binding[]> = await response.json();
  if (envelope.error) {
    throw new Error(envelope.error.message);
  }
  return envelope.data;
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
  const response = await fetch("/api/v1/admin/bindings", {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(vars),
  });
  if (!response.ok) {
    const envelope = await response.json().catch(() => null);
    throw new Error(envelope?.error?.message ?? `HTTP ${response.status}`);
  }
  const envelope: ApiEnvelope<Binding> = await response.json();
  if (envelope.error) {
    throw new Error(envelope.error.message);
  }
  return envelope.data;
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
  const response = await fetch("/api/v1/admin/bindings", {
    method: "DELETE",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(vars),
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(`Failed to delete binding: ${response.status}`);
  }
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
