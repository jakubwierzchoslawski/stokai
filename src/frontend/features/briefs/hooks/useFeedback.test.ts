import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useFeedback', () => {
  afterEach(() => vi.restoreAllMocks());

  it('POSTs to /briefs/{id}/feedback via api()', async () => {
    const mockResponse = { success: true };
    const spy = vi.spyOn(client, 'api').mockResolvedValue(mockResponse);
    const { useFeedback } = await import('./useFeedback');
    const { result } = renderHook(() => useFeedback('b-1'), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.mutateAsync({ feedback_type: 'thumbs_up' });
    });
    expect(spy).toHaveBeenCalledWith(
      '/briefs/b-1/feedback',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
