import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * useAuditTrail.test.ts â€” TDD tests for the useAuditTrail hook.
 *
 * PLAN-F-020 TASK-005
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import * as disclosureApi from '../api/disclosure.api';
import { useAuditTrail } from './useAuditTrail';
import type { AuditTrailData } from '../types/disclosure.types';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function buildAuditTrailData(): AuditTrailData {
  return {
    event_id: 'evt-001',
    prompt_version: 'abc123',
    langfuse_trace_url: 'https://langfuse/traces/xyz',
    analogies: [],
    reasoning_steps: [
      {
        agent_role: 'recommendation_synthesizer',
        step_index: 0,
        content: 'Signal: WATCH',
        tool_calls: ['analogy_lookup'],
      },
      {
        agent_role: 'portfolio_scorer',
        step_index: 1,
        content: 'Scored 3 companies',
        tool_calls: [],
      },
    ],
  };
}

describe('useAuditTrail', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns reasoning_steps as non-empty array when enabled=true', async () => {
    const data = buildAuditTrailData();
    vi.spyOn(disclosureApi, 'fetchAuditTrail').mockResolvedValue(data);

    const { result } = renderHook(() => useAuditTrail('evt-001', true), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.reasoning_steps).toHaveLength(2);
    expect(result.current.data?.prompt_version).toBe('abc123');
  });

  it('does not fire when enabled=false', async () => {
    const spy = vi.spyOn(disclosureApi, 'fetchAuditTrail');

    const { result } = renderHook(() => useAuditTrail('evt-001', false), {
      wrapper: makeWrapper(),
    });

    expect(result.current.data).toBeUndefined();
    expect(spy).not.toHaveBeenCalled();
  });
});
