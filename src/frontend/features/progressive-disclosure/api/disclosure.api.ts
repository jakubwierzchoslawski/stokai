/**
 * disclosure.api.ts — Typed fetch wrappers for the four Progressive Disclosure endpoints.
 *
 * PLAN-F-020 TASK-001
 *
 * Endpoints:
 *   GET /api/v1/events/{id}/popup        → PopupData
 *   GET /api/v1/events/{id}/side-panel   → SidePanelData
 *   GET /api/v1/events/{id}/audit-trail  → AuditTrailData
 *   GET /api/v1/events/{id}/deep-dive    → DeepDiveData | DeepDivePending (202)
 *
 * Each function validates the response shape at runtime. Zod is not assumed to be
 * installed; lightweight inline validators are used instead (matching the pattern in
 * events.api.ts). They can be replaced by Zod schemas when the dep is available.
 */

import type {
  PopupData,
  SidePanelData,
  AuditTrailData,
  DeepDiveData,
  DeepDiveResult,
  TickerDelta,
  SparklinePoint,
  AnalogSummary,
  AffectedCompany,
  SocialPost,
  ReasoningStep,
  ScenarioNode,
} from '../types/disclosure.types';

// ── Typed error ───────────────────────────────────────────────────────────────

export type DisclosureErrorCode =
  | 'UNAUTHORIZED'
  | 'NOT_FOUND'
  | 'SERVER_ERROR'
  | 'NETWORK_ERROR'
  | 'SCHEMA_VIOLATION';

export class DisclosureFetchError extends Error {
  public readonly code: DisclosureErrorCode;
  public readonly status?: number;

  constructor(code: DisclosureErrorCode, message: string, status?: number) {
    super(message);
    this.name = 'DisclosureFetchError';
    this.code = code;
    this.status = status;
  }
}

// ── Auth token ────────────────────────────────────────────────────────────────

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

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// ── Generic fetch helper ──────────────────────────────────────────────────────

async function disclosureFetch(url: string): Promise<{ body: unknown; status: number }> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: authHeaders(),
      credentials: 'include',
    });
  } catch (networkErr) {
    throw new DisclosureFetchError(
      'NETWORK_ERROR',
      `Network request failed: ${String(networkErr)}`,
    );
  }

  if (!response.ok && response.status !== 202) {
    const code: DisclosureErrorCode =
      response.status === 401
        ? 'UNAUTHORIZED'
        : response.status === 404
          ? 'NOT_FOUND'
          : 'SERVER_ERROR';
    throw new DisclosureFetchError(
      code,
      `Request to ${url} returned HTTP ${response.status}`,
      response.status,
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new DisclosureFetchError('SCHEMA_VIOLATION', 'Response body is not valid JSON');
  }

  // Unwrap standard success envelope: { data: ..., meta: ..., error: null }
  const unwrapped =
    body !== null &&
    typeof body === 'object' &&
    'data' in (body as Record<string, unknown>)
      ? (body as Record<string, unknown>)['data']
      : body;

  return { body: unwrapped, status: response.status };
}

// ── Runtime validators ────────────────────────────────────────────────────────

function assertString(v: unknown, field: string): string {
  if (typeof v !== 'string') {
    throw new DisclosureFetchError('SCHEMA_VIOLATION', `Field "${field}" must be a string`);
  }
  return v;
}

function assertNumber(v: unknown, field: string): number {
  if (typeof v !== 'number') {
    throw new DisclosureFetchError('SCHEMA_VIOLATION', `Field "${field}" must be a number`);
  }
  return v;
}

function assertBoolean(v: unknown, field: string): boolean {
  if (typeof v !== 'boolean') {
    throw new DisclosureFetchError('SCHEMA_VIOLATION', `Field "${field}" must be a boolean`);
  }
  return v;
}

function assertArray(v: unknown, field: string): unknown[] {
  if (!Array.isArray(v)) {
    throw new DisclosureFetchError('SCHEMA_VIOLATION', `Field "${field}" must be an array`);
  }
  return v;
}

function assertRecord(v: unknown, field: string): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) {
    throw new DisclosureFetchError('SCHEMA_VIOLATION', `Field "${field}" must be an object`);
  }
  return v as Record<string, unknown>;
}

function validateTickerDelta(raw: unknown): TickerDelta {
  const r = assertRecord(raw, 'TickerDelta');
  return {
    ticker: assertString(r['ticker'], 'ticker'),
    score_delta: assertNumber(r['score_delta'], 'score_delta'),
  };
}

function validateSparklinePoint(raw: unknown): SparklinePoint {
  const r = assertRecord(raw, 'SparklinePoint');
  return {
    ts: assertString(r['ts'], 'ts'),
    close: assertNumber(r['close'], 'close'),
  };
}

function validateAnalogSummary(raw: unknown): AnalogSummary {
  const r = assertRecord(raw, 'AnalogSummary');
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    headline: assertString(r['headline'], 'headline'),
    occurred_at: assertString(r['occurred_at'], 'occurred_at'),
    similarity_score: assertNumber(r['similarity_score'], 'similarity_score'),
  };
}

function validateAffectedCompany(raw: unknown): AffectedCompany {
  const r = assertRecord(raw, 'AffectedCompany');
  return {
    company_id: assertString(r['company_id'], 'company_id'),
    ticker: assertString(r['ticker'], 'ticker'),
    name: assertString(r['name'], 'name'),
    score: assertNumber(r['score'], 'score'),
    delta: assertNumber(r['delta'], 'delta'),
  };
}

function validateSocialPost(raw: unknown): SocialPost {
  const r = assertRecord(raw, 'SocialPost');
  return {
    post_id: assertString(r['post_id'], 'post_id'),
    source: assertString(r['source'], 'source'),
    text: assertString(r['text'], 'text'),
    timestamp: assertString(r['timestamp'], 'timestamp'),
  };
}

function validateReasoningStep(raw: unknown): ReasoningStep {
  const r = assertRecord(raw, 'ReasoningStep');
  return {
    agent_role: assertString(r['agent_role'], 'agent_role'),
    step_index: assertNumber(r['step_index'], 'step_index'),
    content: assertString(r['content'], 'content'),
    tool_calls: assertArray(r['tool_calls'], 'tool_calls').map((t) =>
      assertString(t, 'tool_calls[]'),
    ),
  };
}

function validateScenarioNode(raw: unknown): ScenarioNode {
  const r = assertRecord(raw, 'ScenarioNode');
  return {
    label: assertString(r['label'], 'label'),
    probability: assertNumber(r['probability'], 'probability'),
    description: assertString(r['description'], 'description'),
    children: assertArray(r['children'], 'children').map(validateScenarioNode),
  };
}

function validatePopupDataBase(r: Record<string, unknown>): Omit<PopupData, never> {
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    category: assertArray(r['category'], 'category').map((c) =>
      assertString(c, 'category[]'),
    ),
    intensity: assertNumber(r['intensity'], 'intensity'),
    headline: assertString(r['headline'], 'headline'),
    time_ago: assertString(r['time_ago'], 'time_ago'),
    location: assertString(r['location'], 'location'),
    exposed_holdings_count: assertNumber(r['exposed_holdings_count'], 'exposed_holdings_count'),
    tickers_with_delta: assertArray(r['tickers_with_delta'], 'tickers_with_delta').map(
      validateTickerDelta,
    ),
    action_signal: assertString(r['action_signal'], 'action_signal'),
    confidence: assertNumber(r['confidence'], 'confidence'),
    sample_size: assertNumber(r['sample_size'], 'sample_size'),
    low_sample: assertBoolean(r['low_sample'], 'low_sample'),
  };
}

function validatePopupData(body: unknown): PopupData {
  const r = assertRecord(body, 'PopupData');
  return validatePopupDataBase(r);
}

function validateSidePanelData(body: unknown): SidePanelData {
  const r = assertRecord(body, 'SidePanelData');
  const base = validatePopupDataBase(r);

  const socialPostsRaw = r['social_posts'];
  const social_posts: SocialPost[] | null =
    socialPostsRaw === null || socialPostsRaw === undefined
      ? null
      : assertArray(socialPostsRaw, 'social_posts').map(validateSocialPost);

  return {
    ...base,
    summary: assertString(r['summary'], 'summary'),
    sparklines: assertArray(r['sparklines'], 'sparklines').map((s) => {
      const sr = assertRecord(s, 'sparklines[]');
      return {
        ticker: assertString(sr['ticker'], 'sparklines[].ticker'),
        ohlcv_7d: assertArray(sr['ohlcv_7d'], 'ohlcv_7d').map(validateSparklinePoint),
      };
    }),
    rationale: assertString(r['rationale'], 'rationale'),
    analogies: assertArray(r['analogies'], 'analogies').map(validateAnalogSummary),
    affected_companies: assertArray(r['affected_companies'], 'affected_companies').map(
      validateAffectedCompany,
    ),
    is_contrarian: assertBoolean(r['is_contrarian'], 'is_contrarian'),
    contrarian_callout:
      r['contrarian_callout'] === null || r['contrarian_callout'] === undefined
        ? null
        : assertString(r['contrarian_callout'], 'contrarian_callout'),
    social_posts,
    audit_trail_url: assertString(r['audit_trail_url'], 'audit_trail_url'),
  };
}

function validateAuditTrailData(body: unknown): AuditTrailData {
  const r = assertRecord(body, 'AuditTrailData');
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    prompt_version: assertString(r['prompt_version'], 'prompt_version'),
    langfuse_trace_url: assertString(r['langfuse_trace_url'], 'langfuse_trace_url'),
    analogies: assertArray(r['analogies'], 'analogies').map(validateAnalogSummary),
    reasoning_steps: assertArray(r['reasoning_steps'], 'reasoning_steps').map(
      validateReasoningStep,
    ),
  };
}

function validateDeepDiveData(body: unknown): DeepDiveData {
  const r = assertRecord(body, 'DeepDiveData');
  const scenarioTreeRaw = r['scenario_tree'];
  return {
    event_id: assertString(r['event_id'], 'event_id'),
    memo: assertString(r['memo'], 'memo'),
    scenario_tree:
      scenarioTreeRaw === null || scenarioTreeRaw === undefined
        ? null
        : validateScenarioNode(scenarioTreeRaw),
    analogies: assertArray(r['analogies'], 'analogies').map(validateAnalogSummary),
    affected_companies: assertArray(r['affected_companies'], 'affected_companies').map(
      validateAffectedCompany,
    ),
    generated_at: assertString(r['generated_at'], 'generated_at'),
  };
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Fetch popup-level data for a map event.
 * Renders within 300ms for cached events (TanStack Query staleTime: 30_000).
 */
export async function fetchPopupData(eventId: string): Promise<PopupData> {
  const { body } = await disclosureFetch(
    `/api/v1/events/${encodeURIComponent(eventId)}/popup`,
  );
  return validatePopupData(body);
}

/**
 * Fetch full side-panel data including sparklines, analogies, and rationale.
 * Should only be called when the side panel is opened (lazy).
 */
export async function fetchSidePanelData(eventId: string): Promise<SidePanelData> {
  const { body } = await disclosureFetch(
    `/api/v1/events/${encodeURIComponent(eventId)}/side-panel`,
  );
  return validateSidePanelData(body);
}

/**
 * Fetch the audit trail (reasoning chain + prompt SHA + Langfuse link).
 * Only called when the user opens "Why this read?".
 */
export async function fetchAuditTrail(eventId: string): Promise<AuditTrailData> {
  const { body } = await disclosureFetch(
    `/api/v1/events/${encodeURIComponent(eventId)}/audit-trail`,
  );
  return validateAuditTrailData(body);
}

/**
 * Fetch deep-dive analysis. May return a 202 "pending" response while the
 * deep-dive workflow is running. Callers should poll until DeepDiveData is received.
 */
export async function fetchDeepDive(eventId: string): Promise<DeepDiveResult> {
  const { body, status } = await disclosureFetch(
    `/api/v1/events/${encodeURIComponent(eventId)}/deep-dive`,
  );
  if (status === 202) {
    return { status: 'pending' };
  }
  return validateDeepDiveData(body);
}
