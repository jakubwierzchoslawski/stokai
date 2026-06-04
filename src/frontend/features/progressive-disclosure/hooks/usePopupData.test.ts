/**
 * usePopupData.test.ts — TDD tests for the usePopupData hook.
 *
 * PLAN-F-020 TASK-005
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import * as disclosureApi from '../api/disclosure.api';
import { usePopupData } from './usePopupData';
import type { PopupData } from '../types/disclosure.types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function buildPopupData(overrides: Partial<PopupData> = {}): PopupData {
  return {
    event_id: 'evt-001',
    category: ['GEOPOLITICAL'],
    intensity: 3,
    headline: 'Test event',
    time_ago: '5 minutes ago',
    location: 'Middle East',
    exposed_holdings_count: 2,
    tickers_with_delta: [{ ticker: 'AAPL', score_delta: 1.5 }],
    action_signal: 'WATCH',
    confidence: 0.75,
    sample_size: 8,
    low_sample: false,
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('usePopupData', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('populates data when eventId is provided and fetch resolves', async () => {
    const data = buildPopupData();
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(data);

    const { result } = renderHook(() => usePopupData('evt-001'), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);
  });

  it('does not fire the query when eventId is null', async () => {
    const spy = jest.spyOn(disclosureApi, 'fetchPopupData');

    const { result } = renderHook(() => usePopupData(null), {
      wrapper: makeWrapper(),
    });

    // Query should stay idle — no request made
    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toBeUndefined();
    expect(spy).not.toHaveBeenCalled();
  });

  it('sets isLoading while the fetch is in-flight', async () => {
    // Never resolves
    jest.spyOn(disclosureApi, 'fetchPopupData').mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => usePopupData('evt-001'), {
      wrapper: makeWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });
});
