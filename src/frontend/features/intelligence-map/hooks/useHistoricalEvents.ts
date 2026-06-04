/**
 * useHistoricalEvents.ts — TanStack Query hook for historical event data.
 *
 * When enabled=false (Live mode), returns { events: [], isLoading: false, isError: false }
 * immediately without any network call.
 *
 * When enabled=true, calls GET /api/v1/events?from=&to= and validates the
 * response using the same EventPulse schema used by PLAN-F-019.  Returns
 * events sorted ascending by timestamp for PlaybackEngine compatibility.
 *
 * PLAN-F-021 TASK-005
 */

import { useQuery } from '@tanstack/react-query';
import type { EventPulse } from '../types/map.types';
import type { DateRange } from '../types/time-mode.types';
import { EventFetchError } from '../api/events.api';

// ── Parameters ────────────────────────────────────────────────────────────────

export interface HistoricalEventsParams {
  dateRange: DateRange;
  enabled: boolean;
}

// ── Result ────────────────────────────────────────────────────────────────────

export interface UseHistoricalEventsResult {
  events: EventPulse[];
  isLoading: boolean;
  isError: boolean;
}

// ── Schema validation ─────────────────────────────────────────────────────────
// Reuses the same validation logic as events.api.ts without importing the
// entire module (avoids pulling in window.location dependencies in tests).

function isValidEventPulse(raw: unknown): raw is EventPulse {
  if (typeof raw !== 'object' || raw === null) return false;
  const r = raw as Record<string, unknown>;
  return (
    typeof r['event_id'] === 'string' &&
    Array.isArray(r['category']) &&
    typeof r['intensity'] === 'number' &&
    r['intensity'] >= 1 &&
    r['intensity'] <= 5 &&
    typeof r['headline'] === 'string' &&
    typeof r['timestamp'] === 'string' &&
    typeof r['lat'] === 'number' &&
    typeof r['lon'] === 'number' &&
    typeof r['relevance_window_end'] === 'string' &&
    Array.isArray(r['affected_companies'])
  );
}

function validateEventsResponse(data: unknown): EventPulse[] {
  if (!Array.isArray(data)) {
    throw new EventFetchError('SCHEMA_VIOLATION', 'Events response is not an array');
  }
  for (const item of data) {
    if (!isValidEventPulse(item)) {
      throw new EventFetchError(
        'SCHEMA_VIOLATION',
        `Event failed schema validation: ${JSON.stringify(item)}`,
      );
    }
  }
  return data as EventPulse[];
}

// ── Token accessor ────────────────────────────────────────────────────────────

function getAuthToken(): string {
  try {
    return (
      localStorage.getItem('auth_token') ??
      localStorage.getItem('access_token') ??
      ''
    );
  } catch {
    return '';
  }
}

// ── Fetch function ────────────────────────────────────────────────────────────

async function fetchHistoricalEvents(dateRange: DateRange): Promise<EventPulse[]> {
  const url = new URL('/api/v1/events', window.location.origin);
  url.searchParams.set('from', dateRange.from_date);
  url.searchParams.set('to', dateRange.to_date);

  const token = getAuthToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(url.toString(), { headers, credentials: 'include' });
  } catch (err) {
    throw new EventFetchError('NETWORK_ERROR', `Network request failed: ${String(err)}`);
  }

  if (!response.ok) {
    const code =
      response.status === 401 ? 'UNAUTHORIZED' :
      response.status === 403 ? 'FORBIDDEN' :
      'SERVER_ERROR';
    throw new EventFetchError(code as 'UNAUTHORIZED' | 'FORBIDDEN' | 'SERVER_ERROR', `GET /api/v1/events returned HTTP ${response.status}`, response.status);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new EventFetchError('SCHEMA_VIOLATION', 'Response body is not valid JSON');
  }

  // Unwrap success envelope.
  const payload =
    body !== null && typeof body === 'object' && 'data' in (body as Record<string, unknown>)
      ? (body as Record<string, unknown>)['data']
      : body;

  const validated = validateEventsResponse(payload);
  // Sort ascending by timestamp for PlaybackEngine.
  return validated.sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useHistoricalEvents(
  params: HistoricalEventsParams,
): UseHistoricalEventsResult {
  const { dateRange, enabled } = params;

  const queryResult = useQuery<EventPulse[], Error>({
    queryKey: ['historical-events', dateRange.from_date, dateRange.to_date],
    queryFn: () => fetchHistoricalEvents(dateRange),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 min — historical data does not change.
  });

  if (!enabled) {
    return { events: [], isLoading: false, isError: false };
  }

  return {
    events: queryResult.data ?? [],
    isLoading: queryResult.isLoading,
    isError: queryResult.isError,
  };
}
