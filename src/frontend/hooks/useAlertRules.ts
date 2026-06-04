/**
 * useAlertRules — TanStack Query hook for GET /api/v1/alert-rules.
 *
 * PLAN-F-025 TASK-010
 */
import { useQuery } from '@tanstack/react-query';

export interface AlertRule {
  rule_id: string;
  user_id: string;
  name: string;
  enabled: boolean;
  event_category_filter: string[];
  intensity_min: number;
  ticker_list: string[];
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  per_ticker_interval_hours: number;
  channels: string[];
}

async function fetchAlertRules(): Promise<AlertRule[]> {
  const resp = await fetch('/api/v1/alert-rules', { credentials: 'include' });
  if (!resp.ok) throw new Error(`alert-rules fetch failed: ${resp.status}`);
  const body = await resp.json() as { data: AlertRule[] };
  return body.data;
}

export const ALERT_RULES_QUERY_KEY = ['alert-rules'];

export function useAlertRules() {
  return useQuery<AlertRule[], Error>({
    queryKey: ALERT_RULES_QUERY_KEY,
    queryFn: fetchAlertRules,
  });
}
