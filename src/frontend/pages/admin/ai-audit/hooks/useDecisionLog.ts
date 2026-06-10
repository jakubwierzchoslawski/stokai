/**
 * hooks/useDecisionLog — TanStack Query hook for AI decision log.
 *
 * Supports cursor-based pagination and filter-driven re-fetching.
 * Filter changes reset the cursor.
 *
 * PLAN-F-029 TASK-007
 */
import { useQuery } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import { api } from '@/lib/api/client';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface DecisionLogFilters {
  date_from?: string;
  date_to?: string;
  agent_role?: string;
  model?: string;
  confidence_min?: number;
  confidence_max?: number;
  action_signal?: string;
  company_ticker?: string;
  limit?: number;
}

export interface AIDecisionRow {
  decision_id: string;
  agent_role: string;
  model: string;
  prompt_version: string;
  confidence: number;
  inputs_summary: string;
  output_text_truncated: string;
  action_signal: string | null;
  company_ticker: string | null;
  langfuse_trace_url: string;
  workflow_run_id: string | null;
  created_at: string;
}

export interface DecisionLogPage {
  data: AIDecisionRow[];
  next_cursor: string | null;
  error: null;
}

// ── API fetch ──────────────────────────────────────────────────────────────────

async function fetchDecisions(
  filters: DecisionLogFilters,
  cursor: string | null
): Promise<DecisionLogPage> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.agent_role) params.set('agent_role', filters.agent_role);
  if (filters.model) params.set('model', filters.model);
  if (filters.confidence_min !== undefined)
    params.set('confidence_min', String(filters.confidence_min));
  if (filters.confidence_max !== undefined)
    params.set('confidence_max', String(filters.confidence_max));
  if (filters.action_signal) params.set('action_signal', filters.action_signal);
  if (filters.company_ticker) params.set('company_ticker', filters.company_ticker);
  if (filters.limit) params.set('limit', String(filters.limit));
  if (cursor) params.set('cursor', cursor);

  return api<DecisionLogPage>('/admin/audit/decisions?' + params.toString());
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useDecisionLog(filters: DecisionLogFilters) {
  const [cursor, setCursor] = useState<string | null>(null);

  const queryKey = ['admin', 'audit', 'decisions', filters, cursor] as const;

  const query = useQuery({
    queryKey,
    queryFn: () => fetchDecisions(filters, cursor),
    placeholderData: (prev) => prev, // keepPreviousData equivalent in TanStack Query v5
  });

  const loadNextPage = useCallback(() => {
    if (query.data?.next_cursor) {
      setCursor(query.data.next_cursor);
    }
  }, [query.data?.next_cursor]);

  const resetCursor = useCallback(() => {
    setCursor(null);
  }, []);

  return {
    rows: query.data?.data ?? [],
    nextCursor: query.data?.next_cursor ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    loadNextPage,
    resetCursor,
    refetch: query.refetch,
  };
}

export const DECISION_LOG_QUERY_KEY = ['admin', 'audit', 'decisions'] as const;
