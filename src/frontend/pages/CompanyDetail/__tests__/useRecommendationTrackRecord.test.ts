/**
 * Tests for useRecommendationTrackRecord hook — TDD for TASK-005.
 *
 * PLAN-N-012 AC-001, AC-003
 */
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import {
  useRecommendationTrackRecord,
  trackRecordQueryKey,
} from '../hooks/useRecommendationTrackRecord';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

describe('useRecommendationTrackRecord', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches the correct URL with company_id path segment and limit query param', async () => {
    const companyId = 'abc-123';
    const limit = 25;
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        company_id: companyId,
        company_ticker: 'AAPL',
        entries: [],
        total: 0,
        direction_correct_t1d_pct: null,
        direction_correct_t1w_pct: null,
      }),
    });

    const { result } = renderHook(
      () => useRecommendationTrackRecord({ companyId, limit }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockFetch).toHaveBeenCalledWith(
      `/api/v1/compliance/track-record/${companyId}?limit=${limit}`,
      expect.objectContaining({ credentials: 'include' })
    );
  });

  it('uses cache key ["track-record", companyId]', () => {
    const key = trackRecordQueryKey('my-company');
    expect(key).toEqual(['track-record', 'my-company']);
  });

  it('sets isError=true when the API returns an error response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    const { result } = renderHook(
      () => useRecommendationTrackRecord({ companyId: 'err-company' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
