/**
 * useScoreAtTime.test.ts — TDD tests for useScoreAtTime.
 *
 * PLAN-F-021 TASK-006
 */

import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useScoreAtTime } from './useScoreAtTime';
import type { ScoreAtTime } from '../types/time-mode.types';

// ── MSW server ────────────────────────────────────────────────────────────────

const SCORE_A: ScoreAtTime = {
  company_id: 'company-uuid-A',
  indicator_id: 'ind-1',
  score: 72,
  geo_adjusted: 68,
  computed_at: '2025-01-15T00:00:00Z',
};

const SCORE_B: ScoreAtTime = {
  company_id: 'company-uuid-B',
  indicator_id: 'ind-1',
  score: 45,
  geo_adjusted: 42,
  computed_at: '2025-01-14T00:00:00Z',
};

let networkCallCount = 0;
let lastRequestUrl = '';

const server = setupServer(
  http.get('http://localhost/api/v1/scores/history', ({ request }) => {
    networkCallCount++;
    lastRequestUrl = request.url;
    const url = new URL(request.url);
    const ids = url.searchParams.get('company_ids');
    const at = url.searchParams.get('at');

    if (at === '2025-01-31T00:00:00.000Z' && ids?.includes('company-uuid-A') && ids?.includes('company-uuid-B')) {
      return HttpResponse.json({ data: [SCORE_A, SCORE_B], meta: {}, error: null });
    }
    if (at === '2025-01-31T00:00:00.000Z' && ids?.includes('company-uuid-A')) {
      return HttpResponse.json({ data: [SCORE_A], meta: {}, error: null });
    }
    if (at === '2025-02-28T00:00:00.000Z') {
      return HttpResponse.json({ data: [SCORE_A, SCORE_B], meta: {}, error: null });
    }
    if (at === '2025-03-31T00:00:00.000Z' && ids?.includes('company-uuid-C')) {
      // Company C has no history before this date.
      return HttpResponse.json({ data: [], meta: {}, error: null });
    }
    return HttpResponse.json({ data: [], meta: {}, error: null });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  networkCallCount = 0;
  lastRequestUrl = '';
});
afterAll(() => server.close());

// ── Wrapper ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useScoreAtTime', () => {
  it('enabled=false → no fetch; returns {}', () => {
    const { result } = renderHook(
      () => useScoreAtTime({ companyIds: ['company-uuid-A'], at: '2025-01-31T00:00:00.000Z', enabled: false }),
      { wrapper: createWrapper() },
    );
    expect(result.current.scores).toEqual({});
    expect(result.current.isLoading).toBe(false);
    expect(networkCallCount).toBe(0);
  });

  it('enabled=true, MSW returns 2 score records → scores has 2 keys matching company IDs', async () => {
    const { result } = renderHook(
      () => useScoreAtTime({ companyIds: ['company-uuid-A', 'company-uuid-B'], at: '2025-01-31T00:00:00.000Z', enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(Object.keys(result.current.scores)).toHaveLength(2);
    expect(result.current.scores['company-uuid-A']).toEqual(SCORE_A);
    expect(result.current.scores['company-uuid-B']).toEqual(SCORE_B);
  });

  it('same at and companyIds → TanStack Query cache hit; no second network call', async () => {
    const wrapper = createWrapper();
    const { result: r1 } = renderHook(
      () => useScoreAtTime({ companyIds: ['company-uuid-A'], at: '2025-01-31T00:00:00.000Z', enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(r1.current.isLoading).toBe(false));
    const callsAfterFirst = networkCallCount;

    const { result: r2 } = renderHook(
      () => useScoreAtTime({ companyIds: ['company-uuid-A'], at: '2025-01-31T00:00:00.000Z', enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(r2.current.isLoading).toBe(false));
    // Second hook should be served from cache.
    expect(networkCallCount).toBe(callsAfterFirst);
  });

  it('at changes → new fetch triggered', async () => {
    let at = '2025-01-31T00:00:00.000Z';
    const { result, rerender } = renderHook(
      () => useScoreAtTime({ companyIds: ['company-uuid-A', 'company-uuid-B'], at, enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    const firstCount = networkCallCount;

    at = '2025-02-28T00:00:00.000Z';
    rerender();
    await waitFor(() => expect(networkCallCount).toBeGreaterThan(firstCount));
  });

  it('companyIds changes → new fetch triggered', async () => {
    let ids = ['company-uuid-A'];
    const { result, rerender } = renderHook(
      () => useScoreAtTime({ companyIds: ids, at: '2025-01-31T00:00:00.000Z', enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    const firstCount = networkCallCount;

    ids = ['company-uuid-A', 'company-uuid-B'];
    rerender();
    await waitFor(() => expect(networkCallCount).toBeGreaterThan(firstCount));
  });

  it('company absent from history → company ID absent from scores (no phantom defaults)', async () => {
    const { result } = renderHook(
      () => useScoreAtTime({ companyIds: ['company-uuid-C'], at: '2025-03-31T00:00:00.000Z', enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(Object.keys(result.current.scores)).toHaveLength(0);
    expect(result.current.scores['company-uuid-C']).toBeUndefined();
  });
});
