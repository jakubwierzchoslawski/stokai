/**
 * Tests for WorkflowHistoryPanel and WorkflowDetailDrawer.
 *
 * PLAN-F-029 TASK-011
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/api/client';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const WORKFLOW_ID = 'wf-001';
const INV_ID = 'inv-001';
const TC_ID = 'tc-001';

const MOCK_RUN = {
  workflow_id: WORKFLOW_ID,
  workflow_type: 'mode_b_analysis',
  status: 'completed',
  started_at: '2026-06-04T10:00:00Z',
  completed_at: '2026-06-04T10:01:00Z',
  cost_usd: 0.0523,
  langfuse_trace_id: null,
};

const MOCK_DETAIL = {
  ...MOCK_RUN,
  agent_invocations: [
    {
      invocation_id: INV_ID,
      agent_role_id: 'narrative_writer',
      model_used: 'claude-haiku',
      prompt_version: 'abc1234',
      confidence: 0.85,
      cost_usd: 0.01,
      duration_ms: 500,
      input_tokens: 100,
      output_tokens: 200,
      tool_calls: [
        {
          tool_call_id: TC_ID,
          tool_name: 'search_analogues',
          duration_ms: 100,
          cost_tier: 'free',
          cached: false,
        },
      ],
    },
  ],
  final_state: null,
};

describe('WorkflowHistoryPanel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('renders one table row per WorkflowRunSummary', async () => {
    vi.spyOn(client, 'api').mockResolvedValue({ data: [MOCK_RUN], next_cursor: null, error: null });

    const { WorkflowHistoryPanel } = await import(
      '../../../pages/admin/ai-audit/WorkflowHistoryPanel'
    );
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(WorkflowHistoryPanel)));

    await waitFor(() => {
      expect(screen.getByTestId(`workflow-row-${WORKFLOW_ID}`)).toBeDefined();
    });
  });

  it('clicking a row opens WorkflowDetailDrawer with correct workflow_id', async () => {
    vi.spyOn(client, 'api')
      .mockResolvedValueOnce({ data: [MOCK_RUN], next_cursor: null, error: null })
      .mockResolvedValueOnce(MOCK_DETAIL);

    const { WorkflowHistoryPanel } = await import(
      '../../../pages/admin/ai-audit/WorkflowHistoryPanel'
    );
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(WorkflowHistoryPanel)));

    await waitFor(() => screen.getByTestId(`workflow-row-${WORKFLOW_ID}`));
    fireEvent.click(screen.getByTestId(`workflow-row-${WORKFLOW_ID}`));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-detail-drawer')).toBeDefined();
    });
  });

  it('Re-run button shows confirmation popover before mutation', async () => {
    const spy = vi.spyOn(client, 'api').mockResolvedValue({ data: [MOCK_RUN], next_cursor: null, error: null });

    const { WorkflowHistoryPanel } = await import(
      '../../../pages/admin/ai-audit/WorkflowHistoryPanel'
    );
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(WorkflowHistoryPanel)));

    await waitFor(() => screen.getByTestId(`rerun-btn-${WORKFLOW_ID}`));
    fireEvent.click(screen.getByTestId(`rerun-btn-${WORKFLOW_ID}`));

    expect(screen.getByTestId('rerun-confirm-popover')).toBeDefined();
    // api() should have been called exactly once (the initial list load)
    expect(spy).toHaveBeenCalledOnce();
  });

  it('Re-run success shows new workflow_id in toast', async () => {
    const NEW_WF_ID = 'new-wf-999';
    vi.spyOn(client, 'api')
      .mockResolvedValueOnce({ data: [MOCK_RUN], next_cursor: null, error: null })
      .mockResolvedValueOnce({
        new_workflow_id: NEW_WF_ID,
        workflow_type: 'mode_b_analysis',
        dispatched_at: '2026-06-04T10:05:00Z',
      });

    const { WorkflowHistoryPanel } = await import(
      '../../../pages/admin/ai-audit/WorkflowHistoryPanel'
    );
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(WorkflowHistoryPanel)));

    await waitFor(() => screen.getByTestId(`rerun-btn-${WORKFLOW_ID}`));
    fireEvent.click(screen.getByTestId(`rerun-btn-${WORKFLOW_ID}`));
    fireEvent.click(screen.getByTestId('confirm-rerun'));

    await waitFor(() => {
      expect(screen.getByTestId('rerun-toast').textContent).toContain(NEW_WF_ID);
    });
  });
});

describe('WorkflowDetailDrawer', () => {
  it('renders one accordion per AgentInvocationSummary', async () => {
    const { WorkflowDetailDrawer } = await import(
      '../../../pages/admin/ai-audit/WorkflowDetailDrawer'
    );
    render(
      React.createElement(WorkflowDetailDrawer, {
        detail: MOCK_DETAIL,
        isOpen: true,
        onClose: vi.fn(),
      })
    );

    expect(screen.getByTestId(`invocation-accordion-${INV_ID}`)).toBeDefined();
  });

  it('renders tool calls nested under parent invocation', async () => {
    const { WorkflowDetailDrawer } = await import(
      '../../../pages/admin/ai-audit/WorkflowDetailDrawer'
    );
    render(
      React.createElement(WorkflowDetailDrawer, {
        detail: MOCK_DETAIL,
        isOpen: true,
        onClose: vi.fn(),
      })
    );

    // Expand the accordion
    fireEvent.click(screen.getByTestId(`invocation-accordion-${INV_ID}`).querySelector('button')!);

    await waitFor(() => {
      expect(screen.getByTestId(`tool-call-${TC_ID}`)).toBeDefined();
    });
  });
});
