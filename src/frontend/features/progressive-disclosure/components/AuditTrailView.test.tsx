/**
 * AuditTrailView.test.tsx — TDD tests for AuditTrailView component.
 *
 * PLAN-F-020 TASK-010
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AuditTrailView } from './AuditTrailView';
import * as useAuditTrailModule from '../hooks/useAuditTrail';
import type { AuditTrailData } from '../types/disclosure.types';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function buildAuditTrailData(overrides: Partial<AuditTrailData> = {}): AuditTrailData {
  return {
    event_id: 'evt-001',
    prompt_version: 'abc123def456',
    langfuse_trace_url: 'https://langfuse.example.com/traces/xyz',
    analogies: [
      { event_id: 'old-1', headline: 'Old event A', occurred_at: '2020-01-01', similarity_score: 0.92 },
      { event_id: 'old-2', headline: 'Old event B', occurred_at: '2019-06-15', similarity_score: 0.78 },
    ],
    reasoning_steps: [
      {
        agent_role: 'event_classifier',
        step_index: 0,
        content: 'Classified as GEOPOLITICAL',
        tool_calls: [],
      },
      {
        agent_role: 'recommendation_synthesizer',
        step_index: 1,
        content: 'Signal: WATCH',
        tool_calls: ['analogy_lookup', 'portfolio_scorer'],
      },
    ],
    ...overrides,
  };
}

function mockUseAuditTrail(opts: {
  isLoading?: boolean;
  data?: AuditTrailData;
}) {
  jest.spyOn(useAuditTrailModule, 'useAuditTrail').mockReturnValue({
    data: opts.data,
    isLoading: opts.isLoading ?? false,
    isSuccess: !opts.isLoading && !!opts.data,
    isError: false,
    error: null,
  } as ReturnType<typeof useAuditTrailModule.useAuditTrail>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('AuditTrailView', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('does not render when isOpen=false', () => {
    const spy = jest.spyOn(useAuditTrailModule, 'useAuditTrail');

    render(
      <AuditTrailView eventId="evt-001" isOpen={false} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.queryByTestId('audit-trail-view')).not.toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it('renders prompt SHA when isOpen=true with data', () => {
    mockUseAuditTrail({ data: buildAuditTrailData() });

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('audit-trail-view')).toBeInTheDocument();
    expect(screen.getByTestId('audit-prompt-version')).toHaveTextContent('abc123def456');
  });

  it('renders reasoning steps in order', () => {
    mockUseAuditTrail({ data: buildAuditTrailData() });

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('reasoning-step-0')).toBeInTheDocument();
    expect(screen.getByTestId('reasoning-step-1')).toBeInTheDocument();
    expect(screen.getByTestId('step-agent-role-0')).toHaveTextContent('event_classifier');
    expect(screen.getByTestId('step-agent-role-1')).toHaveTextContent('recommendation_synthesizer');
  });

  it('shows similarity scores as percentages', () => {
    mockUseAuditTrail({ data: buildAuditTrailData() });

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    // Scores are 0.92 → 92% and 0.78 → 78%
    expect(screen.getByText('92%')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
  });

  it('renders Langfuse link with correct href and target=_blank', () => {
    mockUseAuditTrail({ data: buildAuditTrailData() });

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    const link = screen.getByTestId('langfuse-trace-link') as HTMLAnchorElement;
    expect(link).toBeInTheDocument();
    expect(link.href).toBe('https://langfuse.example.com/traces/xyz');
    expect(link.target).toBe('_blank');
    expect(link).toHaveTextContent('View full trace in Langfuse');
  });

  it('omits Langfuse link when langfuse_trace_url is empty', () => {
    mockUseAuditTrail({ data: buildAuditTrailData({ langfuse_trace_url: '' }) });

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.queryByTestId('langfuse-trace-link')).not.toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    mockUseAuditTrail({ data: buildAuditTrailData() });
    const onClose = jest.fn();

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={onClose} />,
      { wrapper: makeWrapper() },
    );

    fireEvent.click(screen.getByTestId('audit-trail-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
