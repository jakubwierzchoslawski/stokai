/**
 * useSidePanelData.test.ts — TDD tests for the useSidePanelData hook.
 *
 * PLAN-F-020 TASK-005
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import * as disclosureApi from '../api/disclosure.api';
import { useSidePanelData } from './useSidePanelData';
import type { SidePanelData } from '../types/disclosure.types';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function buildSidePanelData(): SidePanelData {
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
    summary: 'Summary text',
    sparklines: [],
    rationale: 'Rationale',
    analogies: [],
    affected_companies: [],
    is_contrarian: false,
    contrarian_callout: null,
    social_posts: null,
    audit_trail_url: '/events/evt-001/audit-trail',
  };
}

describe('useSidePanelData', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('does not fire when enabled=false', async () => {
    const spy = jest.spyOn(disclosureApi, 'fetchSidePanelData');

    const { result } = renderHook(() => useSidePanelData('evt-001', false), {
      wrapper: makeWrapper(),
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.data).toBeUndefined();
    expect(spy).not.toHaveBeenCalled();
  });

  it('fires exactly once when enabled=true', async () => {
    const data = buildSidePanelData();
    const spy = jest
      .spyOn(disclosureApi, 'fetchSidePanelData')
      .mockResolvedValue(data);

    const { result } = renderHook(() => useSidePanelData('evt-001', true), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(data);
  });
});
