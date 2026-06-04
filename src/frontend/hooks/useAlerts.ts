/**
 * useAlerts — TanStack Query hook for GET /api/v1/alerts.
 *
 * PLAN-F-025 TASK-009
 */
import { useQuery } from '@tanstack/react-query';

export interface AlertFilters {
  page?: number;
  page_size?: number;
  status?: string;
  action_signal?: string;
  date_from?: string;
  date_to?: string;
}

export interface AlertListItem {
  alert_id: string;
  occurred_at: string;
  event_title: string;
  action_signal: string;
  confidence: number;
  channel: string;
  status: string;
  event_link: string;
  report_link: string | null;
}

export interface AlertListResponse {
  items: AlertListItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

async function fetchAlerts(filters: AlertFilters): Promise<AlertListResponse> {
  const params = new URLSearchParams();
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.page_size !== undefined) params.set('page_size', String(filters.page_size));
  if (filters.status) params.set('status', filters.status);
  if (filters.action_signal) params.set('action_signal', filters.action_signal);
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);

  const resp = await fetch(`/api/v1/alerts?${params.toString()}`, {
    credentials: 'include',
  });
  if (!resp.ok) throw new Error(`alerts fetch failed: ${resp.status}`);
  return resp.json() as Promise<AlertListResponse>;
}

export function useAlerts(filters: AlertFilters = {}) {
  return useQuery<AlertListResponse, Error>({
    queryKey: ['alerts', filters],
    queryFn: () => fetchAlerts(filters),
    staleTime: 30_000,
  });
}
