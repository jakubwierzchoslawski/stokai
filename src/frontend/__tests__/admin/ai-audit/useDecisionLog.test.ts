/**
 * Tests for useDecisionLog hook.
 *
 * PLAN-F-029 TASK-007
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// Wrapper with QueryClient
function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const MOCK_ROW = {
  decision_id: 'dec-001',
  agent_role: 'narrative_writer',
  model: 'claude-haiku',
  prompt_version: 'abc1234',
  confidence: 0.85,
  inputs_summary: 'Summary',
  output_text_truncated: 'Output...',
  action_signal: 'HOLD',
  company_ticker: 'AAPL',
  langfuse_trace_url: 'https://langfuse.example.com/trace/abc',
  workflow_run_id: null,
  created_at: '2026-06-04T10:00:00Z',
};

describe('useDecisionLog', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it('initial load returns first page rows', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: [MOCK_ROW], next_cursor: null, error: null }),
    } as Response);

    const { useDecisionLog } = await import('../../../pages/admin/ai-audit/hooks/useDecisionLog');
    const { result } = renderHook(() => useDecisionLog({}), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0].decision_id).toBe('dec-001');
  });

  it('cursor navigation passes returned cursor to next request', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [MOCK_ROW], next_cursor: 'cursor_page2', error: null }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [], next_cursor: null, error: null }),
      } as Response);

    const { useDecisionLog } = await import('../../../pages/admin/ai-audit/hooks/useDecisionLog');
    const { result } = renderHook(() => useDecisionLog({}), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.nextCursor).toBe('cursor_page2');

    act(() => {
      result.current.loadNextPage();
    });

    await waitFor(() => {
      const url = mockFetch.mock.calls[1]?.[0] as string;
      expect(url).toContain('cursor=cursor_page2');
    });
  });

  it('confidence_min filter is sent in API request', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: [], next_cursor: null, error: null }),
    } as Response);

    const { useDecisionLog } = await import('../../../pages/admin/ai-audit/hooks/useDecisionLog');
    const { result } = renderHook(() => useDecisionLog({ confidence_min: 0.7 }), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain('confidence_min=0.7');
  });
});
