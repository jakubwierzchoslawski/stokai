/**
 * Tests for PromptVersionPanel and RollbackConfirmModal.
 *
 * PLAN-F-029 TASK-009
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

const MOCK_ENTRIES = [
  {
    version_id: 'sha_newer_1234',
    agent_role: 'narrative_writer',
    label_applied: 'production',
    published_at: '2026-06-04T10:00:00Z',
    rolled_back_at: null,
    quality_metrics: { factual_grounding: 0.9, confidence_calibration: 0.85 },
  },
  {
    version_id: 'sha_older_5678',
    agent_role: 'narrative_writer',
    label_applied: 'production',
    published_at: '2026-06-03T10:00:00Z',
    rolled_back_at: '2026-06-04T08:00:00Z',
    quality_metrics: null,
  },
];

describe('PromptVersionPanel', () => {
  beforeEach(() => {
    mockFetch.mockClear();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ data: MOCK_ENTRIES, error: null }),
    } as Response);
  });

  it('renders table rows for each PromptVersionEntry', async () => {
    const { PromptVersionPanel } = await import('../../../admin/ai-audit/PromptVersionPanel');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, {}, React.createElement(PromptVersionPanel)));

    await waitFor(() => {
      expect(screen.getByTestId('prompt-row-sha_newer_1234')).toBeDefined();
      expect(screen.getByTestId('prompt-row-sha_older_5678')).toBeDefined();
    });
  });

  it('row with rolled_back_at does not show Rollback button', async () => {
    const { PromptVersionPanel } = await import('../../../admin/ai-audit/PromptVersionPanel');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, {}, React.createElement(PromptVersionPanel)));

    await waitFor(() => screen.getByTestId('prompt-row-sha_older_5678'));
    // Should not have rollback button for rolled-back version
    expect(screen.queryByTestId('rollback-btn-sha_older_5678')).toBeNull();
  });

  it('row without rolled_back_at shows Rollback button', async () => {
    const { PromptVersionPanel } = await import('../../../admin/ai-audit/PromptVersionPanel');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, {}, React.createElement(PromptVersionPanel)));

    await waitFor(() => screen.getByTestId('rollback-btn-sha_newer_1234'));
    expect(screen.getByTestId('rollback-btn-sha_newer_1234')).toBeDefined();
  });

  it('clicking Rollback opens RollbackConfirmModal with correct SHA', async () => {
    const { PromptVersionPanel } = await import('../../../admin/ai-audit/PromptVersionPanel');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, {}, React.createElement(PromptVersionPanel)));

    await waitFor(() => screen.getByTestId('rollback-btn-sha_newer_1234'));
    fireEvent.click(screen.getByTestId('rollback-btn-sha_newer_1234'));

    await waitFor(() => {
      expect(screen.getByTestId('rollback-confirm-modal')).toBeDefined();
      // The SHA should appear in the modal
      expect(screen.getByTestId('rollback-confirm-modal').textContent).toContain('sha_newer_1234');
    });
  });

  it('displays quality metrics columns when quality_metrics is non-null', async () => {
    const { PromptVersionPanel } = await import('../../../admin/ai-audit/PromptVersionPanel');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, {}, React.createElement(PromptVersionPanel)));

    await waitFor(() => screen.getByTestId('quality-metrics-sha_newer_1234'));
    const metricsCell = screen.getByTestId('quality-metrics-sha_newer_1234');
    expect(metricsCell.textContent).toContain('factual_grounding');
  });
});

describe('RollbackConfirmModal', () => {
  it('displays the 60 seconds SLA callout text', async () => {
    const { RollbackConfirmModal } = await import('../../../admin/ai-audit/RollbackConfirmModal');
    render(
      React.createElement(RollbackConfirmModal, {
        agentRole: 'narrative_writer',
        toVersion: 'abc1234def',
        isOpen: true,
        onClose: vi.fn(),
        onSuccess: vi.fn(),
      })
    );

    expect(screen.getByTestId('sla-callout').textContent).toContain('60 seconds');
  });

  it('Cancel does not call the mutation', async () => {
    const { RollbackConfirmModal } = await import('../../../admin/ai-audit/RollbackConfirmModal');
    const Wrapper = makeWrapper();
    render(
      React.createElement(
        Wrapper,
        {},
        React.createElement(RollbackConfirmModal, {
          agentRole: 'narrative_writer',
          toVersion: 'abc1234def',
          isOpen: true,
          onClose: vi.fn(),
          onSuccess: vi.fn(),
        })
      )
    );

    fireEvent.click(screen.getByTestId('cancel-rollback'));
    // fetch should not have been called
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
