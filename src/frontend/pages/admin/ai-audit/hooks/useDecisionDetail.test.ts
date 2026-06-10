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

describe('useDecisionDetail', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() for GET /admin/audit/decisions/{id} when enabled', async () => {
    const mockDetail = { decision_id: 'd-1', agent_role: 'SCORER' };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockDetail);
    const { useDecisionDetail } = await import('./useDecisionDetail');
    const { result } = renderHook(
      () => useDecisionDetail('d-1', true),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/admin/audit/decisions/d-1');
    expect(result.current.data).toEqual(mockDetail);
  });

  it('does not fire when enabled=false', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue({});
    const { useDecisionDetail } = await import('./useDecisionDetail');
    const { result } = renderHook(
      () => useDecisionDetail('d-1', false),
      { wrapper: makeWrapper() },
    );
    expect(result.current.isLoading).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });
});
