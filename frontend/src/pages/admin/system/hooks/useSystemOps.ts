/**
 * hooks/useSystemOps.ts — TanStack Query hooks for all system-ops endpoints.
 *
 * Covers:
 *   - useIngestionJobs / useTriggerJob
 *   - useCostSummary / useUpdateThreshold
 *   - useTrackedCompanies / useTrackCompany / useUntrackCompany / useSearchCompanies
 *   - useCacheStats / useRefreshCache
 *   - useFeatureFlags / useUpdateFlag
 *
 * PLAN-F-030 TASK-009
 */
import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseMutationResult,
} from "@tanstack/react-query";

const BASE = "/api/v1/admin/system";

// ── Fetch helper ────────────────────────────────────────────────────────────

async function apiFetch<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `HTTP ${res.status}`);
  }
  const body = await res.json();
  return body.data as T;
}

// ── Types ───────────────────────────────────────────────────────────────────

export interface IngestionJob {
  job_id: string;
  name: string;
  schedule: string;
  last_run: string | null;
  next_run: string | null;
  status: "idle" | "running" | "failed";
  error_count: number;
  last_error_trace: string | null;
  updated_at: string;
}

export interface TriggerJobResult {
  job_id: string;
  task_id: string;
  status: string;
}

export interface CostSummary {
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

export interface CompanyList {
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

// ── Ingestion Jobs ─────────────────────────────────────────────────────────

export function useIngestionJobs(): UseQueryResult<IngestionJob[]> {
  return useQuery({
    queryKey: ["admin", "system", "jobs"],
    queryFn: () => apiFetch<IngestionJob[]>(`${BASE}/jobs`),
    refetchInterval: 5000,
  });
}

export function useTriggerJob(): UseMutationResult<
  TriggerJobResult,
  Error,
  string
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      apiFetch<TriggerJobResult>(`${BASE}/jobs/${jobId}/trigger`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "system", "jobs"] });
    },
  });
}

// ── Cost Monitor ───────────────────────────────────────────────────────────

export function useCostSummary(): UseQueryResult<CostSummary> {
  return useQuery({
    queryKey: ["admin", "system", "cost"],
    queryFn: () => apiFetch<CostSummary>(`${BASE}/cost`),
  });
}

export function useUpdateThreshold(): UseMutationResult<
  { threshold_usd: number },
  Error,
  number
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (thresholdUsd: number) =>
      apiFetch<{ threshold_usd: number }>(`${BASE}/cost/threshold`, {
        method: "PATCH",
        body: JSON.stringify({ threshold_usd: thresholdUsd }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "system", "cost"] });
    },
  });
}

// ── Company Universe ───────────────────────────────────────────────────────

export function useTrackedCompanies(
  page = 1,
  pageSize = 50
): UseQueryResult<CompanyList> {
  return useQuery({
    queryKey: ["admin", "system", "companies", page, pageSize],
    queryFn: () =>
      apiFetch<CompanyList>(
        `${BASE}/companies?page=${page}&page_size=${pageSize}`
      ),
  });
}

export function useSearchCompanies(
  q: string
): UseQueryResult<CompanyItem[]> {
  return useQuery({
    queryKey: ["admin", "system", "companies", "search", q],
    queryFn: () =>
      apiFetch<CompanyItem[]>(
        `${BASE}/companies/search?q=${encodeURIComponent(q)}`
      ),
    enabled: q.trim().length > 0,
  });
}

export function useTrackCompany(): UseMutationResult<
  { company_id: string; is_tracked: boolean },
  Error,
  string
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (companyId: string) =>
      apiFetch(`${BASE}/companies/${companyId}/track`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["admin", "system", "companies"],
      });
    },
  });
}

export function useUntrackCompany(): UseMutationResult<
  { company_id: string; is_tracked: boolean },
  Error,
  string
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (companyId: string) =>
      apiFetch(`${BASE}/companies/${companyId}/track`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["admin", "system", "companies"],
      });
    },
  });
}

// ── Cache Inspection ───────────────────────────────────────────────────────

export function useCacheStats(): UseQueryResult<CacheStats> {
  return useQuery({
    queryKey: ["admin", "system", "cache"],
    queryFn: () => apiFetch<CacheStats>(`${BASE}/cache`),
  });
}

export function useRefreshCache(): UseMutationResult<
  { data_type: string; keys_deleted: number },
  Error,
  { data_type: string; company_id?: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { data_type: string; company_id?: string }) =>
      apiFetch(`${BASE}/cache/refresh`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "system", "cache"] });
    },
  });
}

// ── Feature Flags ──────────────────────────────────────────────────────────

export function useFeatureFlags(): UseQueryResult<FeatureFlag[]> {
  return useQuery({
    queryKey: ["admin", "system", "flags"],
    queryFn: () => apiFetch<FeatureFlag[]>(`${BASE}/flags`),
  });
}

export function useUpdateFlag(): UseMutationResult<
  FeatureFlag,
  Error,
  { flag_id: string; enabled: boolean }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ flag_id, enabled }) =>
      apiFetch<FeatureFlag>(`${BASE}/flags/${flag_id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "system", "flags"] });
    },
  });
}
