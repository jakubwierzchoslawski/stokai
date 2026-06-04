/**
 * events.api.ts — GET /api/v1/events wrapper with Zod schema validation.
 *
 * PLAN-F-019 TASK-002
 */

import type { EventPulse } from '../types/map.types';

// ── Query parameters ──────────────────────────────────────────────────────────

export interface EventsQueryParams {
  /** "west,south,east,north" */
  bbox?: string;
  zoom?: number;
  context?: 'global' | 'portfolio' | 'sector';
  sector?: string;
}

// ── Typed error ───────────────────────────────────────────────────────────────

export type EventFetchErrorCode =
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'SERVER_ERROR'
  | 'NETWORK_ERROR'
  | 'SCHEMA_VIOLATION';

export class EventFetchError extends Error {
  public readonly code: EventFetchErrorCode;
  public readonly status?: number;

  constructor(code: EventFetchErrorCode, message: string, status?: number) {
    super(message);
    this.name = 'EventFetchError';
    this.code = code;
    this.status = status;
  }
}

// ── Minimal runtime schema validation (no external Zod dep assumption) ────────
// We implement a lightweight validator that matches the Zod-style API so it can
// be swapped for Zod when the dep is available.

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
    throw new EventFetchError(
      'SCHEMA_VIOLATION',
      'Events response is not an array',
    );
  }
  for (const item of data) {
    if (!isValidEventPulse(item)) {
      throw new EventFetchError(
        'SCHEMA_VIOLATION',
        `Event failed schema validation: missing required field(s). Received: ${JSON.stringify(item)}`,
      );
    }
  }
  return data as EventPulse[];
}

// ── Token accessor ────────────────────────────────────────────────────────────
// Reads the JWT from localStorage under the key used by the auth context.
// Returns an empty string when no token is available (unauthenticated).

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

// ── fetchEvents ───────────────────────────────────────────────────────────────

export async function fetchEvents(
  params: EventsQueryParams,
): Promise<EventPulse[]> {
  const url = new URL('/api/v1/events', window.location.origin);

  if (params.bbox !== undefined) url.searchParams.set('bbox', params.bbox);
  if (params.zoom !== undefined)
    url.searchParams.set('zoom', String(params.zoom));
  if (params.context !== undefined)
    url.searchParams.set('context', params.context);
  if (params.sector !== undefined)
    url.searchParams.set('sector', params.sector);

  const token = getAuthToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url.toString(), { headers, credentials: 'include' });
  } catch (networkErr) {
    throw new EventFetchError(
      'NETWORK_ERROR',
      `Network request failed: ${String(networkErr)}`,
    );
  }

  if (!response.ok) {
    const code: EventFetchErrorCode =
      response.status === 401
        ? 'UNAUTHORIZED'
        : response.status === 403
          ? 'FORBIDDEN'
          : response.status === 404
            ? 'NOT_FOUND'
            : 'SERVER_ERROR';
    throw new EventFetchError(
      code,
      `GET /api/v1/events returned HTTP ${response.status}`,
      response.status,
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new EventFetchError('SCHEMA_VIOLATION', 'Response body is not valid JSON');
  }

  // Unwrap standard success envelope: { data: [...], meta: ..., error: null }
  const payload =
    body !== null &&
    typeof body === 'object' &&
    'data' in (body as Record<string, unknown>)
      ? (body as Record<string, unknown>)['data']
      : body;

  return validateEventsResponse(payload);
}
