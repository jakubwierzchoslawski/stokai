/**
 * useHilQueue — TanStack Query hooks + WebSocket subscription for HIL queue.
 *
 * Provides:
 *   items         — list of pending HIL queue items (auto-refreshes on WS event)
 *   isLoading     — fetch loading state
 *   executeAction — POST /{item_id}/action; invalidates cache on success
 *   pendingCount  — badge count from GET /count (polled every 30 s)
 *
 * WebSocket events: "hil_queue_updated" triggers immediate query invalidation.
 *
 * PLAN-F-013 TASK-008
 */
import { useCallback, useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

const HIL_API_BASE = "/v1/admin/hil";

export interface HILQueueItem {
  item_id: string;
  workflow_run_id: string;
  workflow_type: string;
  user_id: string;
  tenant_id: string;
  confidence: number;
  scheduled_send_at: string;
  status: string;
  reviewer_id: string | null;
  reviewed_at: string | null;
  lc_checkpoint_id: string;
  created_at: string | null;
  // Report preview (populated in detail view)
  report?: Record<string, unknown>;
  hil_reason?: string;
  confidence_scores?: Record<string, number>;
}

export interface HILActionPayload {
  itemId: string;
  action: "approve" | "edit_approve" | "reject" | "reject_with_feedback";
  edited_text?: string;
  feedback_text?: string;
}

async function fetchHilItems(): Promise<HILQueueItem[]> {
  return api<HILQueueItem[]>(`${HIL_API_BASE}/`);
}

async function fetchHilCount(): Promise<number> {
  try {
    const data = await api<{ pending_count?: number }>(`${HIL_API_BASE}/count`);
    return data?.pending_count ?? 0;
  } catch {
    return 0;
  }
}

async function postHilAction(payload: HILActionPayload) {
  const { itemId, action, edited_text, feedback_text } = payload;
  return api<unknown>(`${HIL_API_BASE}/${itemId}/action`, {
    method: "POST",
    body: JSON.stringify({ action, edited_text, feedback_text }),
  });
}

export const HIL_ITEMS_QUERY_KEY = ["hil", "items"] as const;
export const HIL_COUNT_QUERY_KEY = ["hil", "count"] as const;

export function useHilQueue() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  // ── Fetch pending items ────────────────────────────────────────────────────
  const {
    data: items,
    isLoading,
    error,
  } = useQuery({
    queryKey: HIL_ITEMS_QUERY_KEY,
    queryFn: fetchHilItems,
    staleTime: 30_000,
  });

  // ── Fetch pending count (for badge, polled every 30 s) ────────────────────
  const { data: pendingCount = 0 } = useQuery({
    queryKey: HIL_COUNT_QUERY_KEY,
    queryFn: fetchHilCount,
    refetchInterval: 30_000,
  });

  // ── WebSocket: real-time push refresh ─────────────────────────────────────
  useEffect(() => {
    const wsUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/admin`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as { type: string };
        if (msg.type === "hil_queue_updated") {
          void queryClient.invalidateQueries({ queryKey: HIL_ITEMS_QUERY_KEY });
          void queryClient.invalidateQueries({ queryKey: HIL_COUNT_QUERY_KEY });
        }
      } catch {
        // Non-JSON messages are ignored
      }
    };

    ws.onerror = () => {
      // WebSocket unavailable — fall back to polling (no functional regression)
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [queryClient]);

  // ── Execute action ─────────────────────────────────────────────────────────
  const mutation = useMutation({
    mutationFn: postHilAction,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: HIL_ITEMS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: HIL_COUNT_QUERY_KEY });
    },
  });

  const executeAction = useCallback(
    (payload: HILActionPayload) => mutation.mutateAsync(payload),
    [mutation],
  );

  return {
    items: items ?? [],
    isLoading,
    error,
    pendingCount,
    executeAction,
    isActing: mutation.isPending,
    actionError: mutation.error,
  };
}
