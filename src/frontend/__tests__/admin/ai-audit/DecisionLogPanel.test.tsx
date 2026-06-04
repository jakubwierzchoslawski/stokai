/**
 * Tests for DecisionLogPanel and DecisionDetailDrawer components.
 *
 * PLAN-F-029 TASK-007
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

describe('DecisionLogPanel', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it('renders a table row for each returned decision', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [MOCK_ROW], next_cursor: null, error: null }),
      } as Response);

    const { DecisionLogPanel } = await import('../../../admin/ai-audit/DecisionLogPanel');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, {}, React.createElement(DecisionLogPanel)));

    await waitFor(() => {
      expect(screen.getByTestId(`decision-row-dec-001`)).toBeDefined();
    });
  });

  it('clicking a table row opens DecisionDetailDrawer', async () => {
    const DETAIL = {
      ...MOCK_ROW,
      inputs_full: '{"event": "data"}',
      retrieved_analogs: [],
      output_text: 'Full output',
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [MOCK_ROW], next_cursor: null, error: null }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: DETAIL, error: null }),
      } as Response);

    const { DecisionLogPanel } = await import('../../../admin/ai-audit/DecisionLogPanel');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, {}, React.createElement(DecisionLogPanel)));

    await waitFor(() => screen.getByTestId('decision-row-dec-001'));
    fireEvent.click(screen.getByTestId('decision-row-dec-001'));

    await waitFor(() => {
      expect(screen.getByTestId('decision-detail-drawer')).toBeDefined();
    });
  });
});

describe('DecisionDetailDrawer', () => {
  it('renders langfuse_trace_url as anchor with target=_blank', async () => {
    const { DecisionDetailDrawer } = await import('../../../admin/ai-audit/DecisionDetailDrawer');

    const detail = {
      decision_id: 'dec-001',
      agent_role: 'narrative_writer',
      model: 'claude-haiku',
      prompt_version: 'abc1234',
      confidence: 0.85,
      inputs_summary: 'Summary',
      inputs_full: '{"event": "data"}',
      retrieved_analogs: [],
      action_signal: null,
      company_ticker: 'AAPL',
      output_text: 'Full output',
      langfuse_trace_url: 'https://langfuse.example.com/trace/abc',
      workflow_run_id: null,
      created_at: '2026-06-04T10:00:00Z',
    };

    render(
      React.createElement(DecisionDetailDrawer, {
        decision: detail,
        isOpen: true,
        onClose: vi.fn(),
        onOverride: vi.fn(),
      })
    );

    const link = screen.getByTestId('langfuse-trace-link');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('href')).toBe('https://langfuse.example.com/trace/abc');
  });
});

describe('DecisionLogFilter', () => {
  it('Clear button resets all filter fields', async () => {
    const onApply = vi.fn();
    const onClear = vi.fn();

    const { DecisionLogFilter } = await import('../../../admin/ai-audit/DecisionLogFilter');
    render(React.createElement(DecisionLogFilter, { onApply, onClear }));

    // Set a filter value
    const ticker = screen.getByTestId('filter-company-ticker') as HTMLInputElement;
    fireEvent.change(ticker, { target: { value: 'AAPL' } });
    expect(ticker.value).toBe('AAPL');

    // Click Clear
    fireEvent.click(screen.getByTestId('filter-clear'));
    expect(onClear).toHaveBeenCalledOnce();
    expect(ticker.value).toBe('');
  });
});
