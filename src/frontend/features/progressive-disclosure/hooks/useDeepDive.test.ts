import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
/**
 * useDeepDive.test.ts â€” TDD tests for the useDeepDive hook.
 *
 * PLAN-F-020 TASK-005
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import * as disclosureApi from '../api/disclosure.api';
import { useDeepDive } from './useDeepDive';
import type { DeepDiveData, DeepDivePending } from '../types/disclosure.types';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function buildDeepDiveData(): DeepDiveData {
  return {
    event_id: 'evt-001',
    memo: 'Full analysis memo.',
    scenario_tree: null,
    analogies: [],
    affected_companies: [],
    generated_at: new Date().toISOString(),
  };
}

describe('useDeepDive', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('returns pending state when API returns 202 pending', async () => {
    const pending: DeepDivePending = { status: 'pending' };
    vi.spyOn(disclosureApi, 'fetchDeepDive').mockResolvedValue(pending);

    const { result } = renderHook(() => useDeepDive('evt-001', true), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ status: 'pending' });
  });

  it('does not refetch when API returns completed DeepDiveData', async () => {
    const data = buildDeepDiveData();
    const spy = vi
      .spyOn(disclosureApi, 'fetchDeepDive')
      .mockResolvedValue(data);

    const { result } = renderHook(() => useDeepDive('evt-001', true), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);

    // Advance time â€” should NOT re-fetch since data is not pending
    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    // Still only called once
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('eventually resolves to DeepDiveData after initial pending response', async () => {
    const pending: DeepDivePending = { status: 'pending' };
    const data = buildDeepDiveData();

    let callCount = 0;
    vi.spyOn(disclosureApi, 'fetchDeepDive').mockImplementation(async () => {
      callCount++;
      return callCount === 1 ? pending : data;
    });

    const { result } = renderHook(() => useDeepDive('evt-001', true), {
      wrapper: makeWrapper(),
    });

    // First call returns pending
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(pending);

    // Advance timer to trigger refetch
    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    // Second call should return data
    await waitFor(() => {
      const d = result.current.data;
      return d !== undefined && 'memo' in d;
    });
    expect(result.current.data).toEqual(data);
  });
});
