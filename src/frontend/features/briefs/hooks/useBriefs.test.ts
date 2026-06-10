import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';
import type { BriefListResponse } from '../briefs.types';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const PAGE: BriefListResponse = {
  data: { items: [], next_cursor: null },
  meta: {},
  error: null,
};

describe('useBriefs', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() with the correct path when briefType is set', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue(PAGE);
    const { useBriefs } = await import('./useBriefs');
    const { result } = renderHook(() => useBriefs({ briefType: 'morning_brief' }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(expect.stringContaining('/briefs?'));
    expect(spy).toHaveBeenCalledWith(expect.stringContaining('type=morning_brief'));
  });

  it('does not include type param when briefType is undefined', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue(PAGE);
    const { useBriefs } = await import('./useBriefs');
    const { result } = renderHook(() => useBriefs(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const calledPath = (spy.mock.calls[0] as string[])[0];
    expect(calledPath).not.toContain('type=');
  });
});
