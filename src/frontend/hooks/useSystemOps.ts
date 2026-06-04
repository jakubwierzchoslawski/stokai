/**
 * hooks/useSystemOps — TanStack Query hooks for the System Operations panel.
 *
 * PLAN-F-030 TASK-009
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// ── Query keys ─────────────────────────────────────────────────────────────────

export const SYSTEM_JOBS_KEY = ['admin', 'system', 'jobs'] as const;
export const SYSTEM_COST_KEY = ['admin', 'system', 'cost'] as const;
export const SYSTEM_COMPANIES_KEY = ['admin', 'system', 'companies'] as const;
export const SYSTEM_CACHE_KEY = ['admin', 'system', 'cache'] as const;
export const SYSTEM_FLAGS_KEY = ['admin', 'system', 'flags'] as const;

// ── Types ───────────────────────────────────────────────────────────────────────

export interface IngestionJob {
  job_id: string;
  name: string;
  schedule: string;
  last_run: string | null;
  next_run: string | null;
  status: 'idle' | 'running' | 'failed';
  error_count: number;
  last_error_trace: string | null;
  updated_at: string;
}

export interface CostData {
  spend_usd: number;
  threshold_usd: number;
  pct_used: number;
  warning_active: boolean;
  hard_stop_active: boolean;
  by_source: Array<{ source: string; total_cost_usd: number }>;
  by_model: Array<{ model: string; total_cost_usd: number }>;
  by_workflow: Array<{ workflow_type: string; total_cost_usd: number }>;
  daily_totals: Array<{ date: string; total_cost_usd: number }>;
}

export interface CompanyItem {
  company_id: string;
  ticker: string;
  name: string;
  is_tracked: boolean;
  sector_gics?: string;
}

export interface CompanyListResponse {
  items: CompanyItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CacheStats {
  price_bars_count: number;
  embeddings_count: number;
  event_data_count: number;
  total_redis_memory_bytes: number;
}

export interface FeatureFlag {
  flag_id: string;
  environment: string;
  enabled: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

// ── API helpers ────────────────────────────────────────────────────────────────

const BASE = '/api/v1/admin/system';

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.error?.message ?? `HTTP ${resp.status}`);
  }
  const body = await resp.json();
  return body.data as T;
}

// ── Ingestion Jobs ─────────────────────────────────────────────────────────────

export function useIngestionJobs() {
  return useQuery<IngestionJob[]>({
    queryKey: SYSTEM_JOBS_KEY,
    queryFn: () => apiFetch<IngestionJob[]>(`${BASE}/jobs`),
    refetchInterval: 30_000,
  });
}

export function useTriggerJob() {
  const queryClient = useQueryClient();
  return useMutation<{ task_id: string; job_id: string }, Error, { job_id: string }>({
    mutationFn: ({ job_id }) =>
      apiFetch(`${BASE}/jobs/${job_id}/trigger`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYSTEM_JOBS_KEY });
    },
  });
}

// ── Cost Monitor ───────────────────────────────────────────────────────────────

export function useCostData() {
  return useQuery<CostData>({
    queryKey: SYSTEM_COST_KEY,
    queryFn: () => apiFetch<CostData>(`${BASE}/cost`),
    refetchInterval: 60_000,
  });
}

export function useUpdateThreshold() {
  const queryClient = useQueryClient();
  return useMutation<{ threshold_usd: number }, Error, { threshold_usd: number }>({
    mutationFn: ({ threshold_usd }) =>
      apiFetch(`${BASE}/cost/threshold`, {
        method: 'PATCH',
        body: JSON.stringify({ threshold_usd }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYSTEM_COST_KEY });
    },
  });
}

// ── Company Universe ───────────────────────────────────────────────────────────

export function useTrackedCompanies(page = 1, pageSize = 50) {
  return useQuery<CompanyListResponse>({
    queryKey: [...SYSTEM_COMPANIES_KEY, page, pageSize],
    queryFn: () =>
      apiFetch<CompanyListResponse>(
        `${BASE}/companies?page=${page}&page_size=${pageSize}`
      ),
  });
}

export function useTrackCompany() {
  const queryClient = useQueryClient();
  return useMutation<{ is_tracked: boolean }, Error, { company_id: string }>({
    mutationFn: ({ company_id }) =>
      apiFetch(`${BASE}/companies/${company_id}/track`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYSTEM_COMPANIES_KEY });
    },
  });
}

export function useUntrackCompany() {
  const queryClient = useQueryClient();
  return useMutation<{ is_tracked: boolean }, Error, { company_id: string }>({
    mutationFn: ({ company_id }) =>
      apiFetch(`${BASE}/companies/${company_id}/track`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYSTEM_COMPANIES_KEY });
    },
  });
}

export function useSearchCompanies(query: string) {
  return useQuery<CompanyItem[]>({
    queryKey: [...SYSTEM_COMPANIES_KEY, 'search', query],
    queryFn: () =>
      apiFetch<CompanyItem[]>(`${BASE}/companies/search?q=${encodeURIComponent(query)}`),
    enabled: query.length >= 1,
  });
}

// ── Cache Inspection ───────────────────────────────────────────────────────────

export function useCacheStats() {
  return useQuery<CacheStats>({
    queryKey: SYSTEM_CACHE_KEY,
    queryFn: () => apiFetch<CacheStats>(`${BASE}/cache`),
    refetchInterval: 30_000,
  });
}

export function useForceRefreshCache() {
  const queryClient = useQueryClient();
  return useMutation<
    { data_type: string; keys_deleted: number },
    Error,
    { data_type: string; company_id?: string }
  >({
    mutationFn: (payload) =>
      apiFetch(`${BASE}/cache/refresh`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYSTEM_CACHE_KEY });
    },
  });
}

// ── Feature Flags ──────────────────────────────────────────────────────────────

export function useFeatureFlags() {
  return useQuery<FeatureFlag[]>({
    queryKey: SYSTEM_FLAGS_KEY,
    queryFn: () => apiFetch<FeatureFlag[]>(`${BASE}/flags`),
  });
}

export function useSetFeatureFlag() {
  const queryClient = useQueryClient();
  return useMutation<
    FeatureFlag,
    Error,
    { flag_id: string; enabled: boolean }
  >({
    mutationFn: ({ flag_id, enabled }) =>
      apiFetch(`${BASE}/flags/${flag_id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SYSTEM_FLAGS_KEY });
    },
  });
}
