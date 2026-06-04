/**
 * useAntiFatigueSettings — TanStack Query hook for GET/PATCH anti-fatigue settings.
 *
 * PLAN-F-025 TASK-011
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

export interface AntiFatigueSettings {
  daily_push_limit: number;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  dedup_window_minutes: number;
}

export interface UpdateAntiFatiguePayload {
  daily_push_limit?: number;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  dedup_window_minutes?: number;
}

const ANTI_FATIGUE_QUERY_KEY = ['anti-fatigue-settings'];

async function fetchSettings(): Promise<AntiFatigueSettings> {
  const resp = await fetch('/api/v1/settings/anti-fatigue', { credentials: 'include' });
  if (!resp.ok) throw new Error(`anti-fatigue fetch failed: ${resp.status}`);
  const body = await resp.json() as { data: AntiFatigueSettings };
  return body.data;
}

async function patchSettings(payload: UpdateAntiFatiguePayload): Promise<AntiFatigueSettings> {
  const resp = await fetch('/api/v1/settings/anti-fatigue', {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({})) as { detail?: { message?: string } };
    throw new Error(body?.detail?.message ?? `anti-fatigue update failed: ${resp.status}`);
  }
  const body = await resp.json() as { data: AntiFatigueSettings };
  return body.data;
}

export function useAntiFatigueSettings() {
  const queryClient = useQueryClient();

  const query = useQuery<AntiFatigueSettings, Error>({
    queryKey: ANTI_FATIGUE_QUERY_KEY,
    queryFn: fetchSettings,
  });

  const mutation = useMutation({
    mutationFn: patchSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(ANTI_FATIGUE_QUERY_KEY, updated);
    },
  });

  return { ...query, updateSettings: mutation };
}
