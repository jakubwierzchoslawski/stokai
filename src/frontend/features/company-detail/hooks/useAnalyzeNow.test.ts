import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import * as client from '@/lib/api/client';
import * as ws from '@/lib/api/ws';

describe('useAnalyzeNow', () => {
  afterEach(() => vi.restoreAllMocks());

  it('calls api() to POST trigger and apiSocket() to open the WebSocket', async () => {
    vi.spyOn(client, 'api').mockResolvedValue({ run_id: 'run-1', company_id: 'c-1', status: 'running' });
    const closeMock = vi.fn();
    const socketSpy = vi.spyOn(ws, 'apiSocket').mockReturnValue({ close: closeMock });

    const { useAnalyzeNow } = await import('./useAnalyzeNow');
    const { result } = renderHook(() => useAnalyzeNow({ companyId: 'c-1' }));

    await act(async () => { await result.current.trigger(); });

    expect(client.api).toHaveBeenCalledWith(
      '/companies/c-1/analysis',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(socketSpy).toHaveBeenCalledWith(
      '/ws/analysis/run-1',
      expect.objectContaining({ onMessage: expect.any(Function), onError: expect.any(Function) }),
    );
    expect(result.current.isLoading).toBe(true);
    expect(result.current.runId).toBe('run-1');
  });

  it('sets error without entering loading on 409 conflict', async () => {
    const { ApiError } = await import('@/lib/api/errors');
    vi.spyOn(client, 'api').mockRejectedValue(new ApiError(409, 'CONFLICT', 'Analysis in progress'));

    const { useAnalyzeNow } = await import('./useAnalyzeNow');
    const { result } = renderHook(() => useAnalyzeNow({ companyId: 'c-1' }));

    await act(async () => { await result.current.trigger(); });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toContain('already in progress');
  });
});
