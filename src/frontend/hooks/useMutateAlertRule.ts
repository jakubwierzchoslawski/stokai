/**
 * useMutateAlertRule — mutations for alert rule CRUD.
 *
 * Exposes createRule, updateRule, deleteRule.
 * Each mutation invalidates the useAlertRules cache on success.
 *
 * PLAN-F-025 TASK-010
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ALERT_RULES_QUERY_KEY, AlertRule } from './useAlertRules';

export interface CreateAlertRulePayload {
  name: string;
  event_category_filter: string[];
  intensity_min: number;
  ticker_list: string[];
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  per_ticker_interval_hours: number;
  channels: string[];
}

export interface UpdateAlertRulePayload {
  rule_id: string;
  name?: string;
  enabled?: boolean;
  event_category_filter?: string[];
  intensity_min?: number;
  ticker_list?: string[];
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  per_ticker_interval_hours?: number;
  channels?: string[];
}

async function apiCreateRule(payload: CreateAlertRulePayload): Promise<{ rule_id: string }> {
  const resp = await fetch('/api/v1/alert-rules', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({})) as { detail?: { message?: string } };
    throw new Error(body?.detail?.message ?? `create rule failed: ${resp.status}`);
  }
  const body = await resp.json() as { data: { rule_id: string } };
  return body.data;
}

async function apiUpdateRule({ rule_id, ...patch }: UpdateAlertRulePayload): Promise<void> {
  const resp = await fetch(`/api/v1/alert-rules/${rule_id}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({})) as { detail?: { message?: string } };
    throw new Error(body?.detail?.message ?? `update rule failed: ${resp.status}`);
  }
}

async function apiDeleteRule(rule_id: string): Promise<void> {
  const resp = await fetch(`/api/v1/alert-rules/${rule_id}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!resp.ok) {
    throw new Error(`delete rule failed: ${resp.status}`);
  }
}

export function useMutateAlertRule() {
  const queryClient = useQueryClient();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ALERT_RULES_QUERY_KEY });

  const createRule = useMutation({
    mutationFn: apiCreateRule,
    onSuccess: invalidate,
  });

  const updateRule = useMutation({
    mutationFn: apiUpdateRule,
    onSuccess: invalidate,
  });

  const deleteRule = useMutation({
    mutationFn: apiDeleteRule,
    onSuccess: invalidate,
  });

  return { createRule, updateRule, deleteRule };
}
