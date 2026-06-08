/**
 * Tests for OverrideModal component and useAdminOverride hook.
 *
 * PLAN-F-029 TASK-008
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

const MOCK_DECISION = {
  decision_id: 'dec-001',
  agent_role: 'narrative_writer',
  model: 'claude-haiku',
  prompt_version: 'abc1234',
  confidence: 0.75,
  inputs_summary: 'Summary',
  inputs_full: '{"event": "data"}',
  retrieved_analogs: [],
  action_signal: null,
  company_ticker: 'AAPL',
  output_text: 'Original output text that will be overridden',
  langfuse_trace_url: 'https://langfuse.example.com/trace/abc',
  workflow_run_id: null,
  created_at: '2026-06-04T10:00:00Z',
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('OverrideModal', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  async function renderModal(onClose = vi.fn(), onSuccess = vi.fn()) {
    const { OverrideModal } = await import('../../../pages/admin/ai-audit/OverrideModal');
    const Wrapper = makeWrapper();
    render(
      React.createElement(
        Wrapper,
        {},
        React.createElement(OverrideModal, {
          decision: MOCK_DECISION,
          isOpen: true,
          onClose,
          onSuccess,
        })
      )
    );
  }

  it('submit button is disabled when corrected_output is empty', async () => {
    await renderModal();
    const btn = screen.getByTestId('submit-override') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('submit button is disabled when override_reason is fewer than 20 chars', async () => {
    await renderModal();
    const corrected = screen.getByTestId('corrected-output');
    const reason = screen.getByTestId('override-reason');
    fireEvent.change(corrected, { target: { value: 'A corrected output text' } });
    fireEvent.change(reason, { target: { value: 'Short' } });
    const btn = screen.getByTestId('submit-override') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('calls mutation with correct args on valid submit', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          decision_id: 'dec-001',
          feedback_id: 'fb-001',
          golden_dataset_candidate_id: 'gdc-001',
          proposed_prompt_adjustment: 'Review prompt for narrative_writer',
          status: 'pending_review',
        },
        error: null,
      }),
    } as Response);

    await renderModal();

    fireEvent.change(screen.getByTestId('corrected-output'), {
      target: { value: 'A much better corrected output text' },
    });
    fireEvent.change(screen.getByTestId('override-reason'), {
      target: { value: 'The original output was factually incorrect and misleading' },
    });

    const btn = screen.getByTestId('submit-override') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledOnce();
      const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
      expect(body.decision_id).toBe('dec-001');
      expect(body.corrected_output).toBe('A much better corrected output text');
    });
  });

  it('displays proposed_prompt_adjustment after successful submission', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          decision_id: 'dec-001',
          feedback_id: 'fb-001',
          golden_dataset_candidate_id: 'gdc-001',
          proposed_prompt_adjustment: 'Review prompt for narrative_writer confidence 0.75',
          status: 'pending_review',
        },
        error: null,
      }),
    } as Response);

    await renderModal();

    fireEvent.change(screen.getByTestId('corrected-output'), {
      target: { value: 'A much better corrected output text' },
    });
    fireEvent.change(screen.getByTestId('override-reason'), {
      target: { value: 'The original output was factually incorrect and misleading' },
    });
    fireEvent.click(screen.getByTestId('submit-override'));

    await waitFor(() => {
      expect(screen.getByTestId('proposed-adjustment')).toBeDefined();
      expect(screen.getByTestId('proposed-adjustment').textContent).toContain(
        'Review prompt for narrative_writer'
      );
    });
  });

  it('displays error message when mutation returns non-2xx', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: { message: 'Decision not found' } }),
    } as Response);

    await renderModal();

    fireEvent.change(screen.getByTestId('corrected-output'), {
      target: { value: 'A much better corrected output text' },
    });
    fireEvent.change(screen.getByTestId('override-reason'), {
      target: { value: 'The original output was factually incorrect and misleading' },
    });
    fireEvent.click(screen.getByTestId('submit-override'));

    await waitFor(() => {
      expect(screen.getByTestId('override-error')).toBeDefined();
    });
  });
});
