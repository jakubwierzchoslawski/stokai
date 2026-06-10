import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useCompanyDetail', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() with /companies/{id}/detail', async () => {
    const mockData = { company_id: 'c-1', name: 'Acme' };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockData);
    const { useCompanyDetail } = await import('./useCompanyDetail');
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: 'c-1' }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/companies/c-1/detail');
    expect(result.current.data).toEqual(mockData);
  });

  it('includes profile_id query param when provided', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue({});
    const { useCompanyDetail } = await import('./useCompanyDetail');
    const { result } = renderHook(
      () => useCompanyDetail({ companyId: 'c-1', profileId: 'p-42' }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/companies/c-1/detail?profile_id=p-42');
  });
});
