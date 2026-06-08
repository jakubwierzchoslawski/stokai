import { describe, it, expect, vi, beforeEach , type Mock } from 'vitest';
/**
 * Unit tests for useCompanyDetail hook.
 *
 * Tests:
 * - Makes GET request to correct URL
 * - Profile change causes cache key to differ (refetch)
 *
 * PLAN-F-023 TASK-005
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useCompanyDetail, companyDetailQueryKey } from '../../../src/frontend/pages/CompanyDetail/hooks/useCompanyDetail';

// â”€â”€ Fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const COMPANY_ID = 'c1c1c1c1-0000-0000-0000-000000000001';
const PROFILE_ID = 'aaaaaaaa-0000-0000-0000-000000000001';

const MOCK_DETAIL = {
  company_id: COMPANY_ID,
  ticker: 'ACME',
  name: 'Acme Corp',
  sector: 'Technology',
  market_cap: 5_000_000_000,
  fundamentals: {
    pe_ratio: 20.5,
    eps: 3.14,
    revenue: 1_000_000,
    debt_to_equity: 0.5,
    source: 'fmp',
    as_of: '2024-01-01T00:00:00Z',
  },
  scores: [],
  active_events: [],
  analysis_history: [],
  track_record: [],
  directional_accuracy_t1d: null,
};

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  }
  return { Wrapper, queryClient };
}

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('useCompanyDetail', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('makes GET request to the company detail endpoint', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_DETAIL,
    } as Response);

    const { Wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: COMPANY_ID }),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/v1/companies/${COMPANY_ID}/detail`),
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('includes profile_id in URL when provided', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_DETAIL,
    } as Response);

    const { Wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: COMPANY_ID, profileId: PROFILE_ID }),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const calledUrl = (global.fetch as Mock).mock.calls[0][0] as string;
    expect(calledUrl).toContain(`profile_id=${PROFILE_ID}`);
  });

  it('uses different query keys for different profile IDs', () => {
    const key1 = companyDetailQueryKey(COMPANY_ID, undefined);
    const key2 = companyDetailQueryKey(COMPANY_ID, PROFILE_ID);

    expect(JSON.stringify(key1)).not.toEqual(JSON.stringify(key2));
  });

  it('returns data from the API response', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_DETAIL,
    } as Response);

    const { Wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: COMPANY_ID }),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.ticker).toBe('ACME');
    expect(result.current.data?.name).toBe('Acme Corp');
  });

  it('is disabled when companyId is empty', async () => {
    global.fetch = vi.fn();

    const { Wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: '' }),
      { wrapper: Wrapper },
    );

    // Should not fetch
    expect(result.current.fetchStatus).toBe('idle');
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
