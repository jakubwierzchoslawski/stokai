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

describe('useBriefDetail', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() with the correct brief ID path', async () => {
    const mockData = { id: 'b-1', title: 'Test Brief' };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockData);
    const { useBriefDetail } = await import('./useBriefDetail');
    const { result } = renderHook(() => useBriefDetail('b-1'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/briefs/b-1');
    expect(result.current.data).toEqual(mockData);
  });

  it('does not fire when briefId is empty', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue({});
    const { useBriefDetail } = await import('./useBriefDetail');
    const { result } = renderHook(() => useBriefDetail(''), { wrapper: makeWrapper() });
    expect(result.current.isLoading).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });
});
