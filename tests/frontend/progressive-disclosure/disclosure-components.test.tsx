/**
 * disclosure-components.test.tsx — Tests for LowSampleDisclaimer, ContrarianCallout,
 * SidePanelAnalogies, and AuditTrailView components.
 *
 * PLAN-F-020 TASK-007, TASK-008, TASK-010 (TDD)
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { LowSampleDisclaimer } from '../../../src/frontend/features/progressive-disclosure/components/LowSampleDisclaimer';
import { ContrarianCallout } from '../../../src/frontend/features/progressive-disclosure/components/ContrarianCallout';
import { SidePanelAnalogies } from '../../../src/frontend/features/progressive-disclosure/components/SidePanelAnalogies';
import { AuditTrailView } from '../../../src/frontend/features/progressive-disclosure/components/AuditTrailView';
import * as useAuditTrailModule from '../../../src/frontend/features/progressive-disclosure/hooks/useAuditTrail';
import type { AnalogSummary, AuditTrailData } from '../../../src/frontend/features/progressive-disclosure/types/disclosure.types';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

// ── LowSampleDisclaimer ───────────────────────────────────────────────────────

describe('LowSampleDisclaimer', () => {
  it('renders the disclaimer text with role=alert', () => {
    render(<LowSampleDisclaimer />);
    expect(screen.getByTestId('low-sample-disclaimer')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Low sample/)).toBeInTheDocument();
    expect(screen.getByText(/fewer than 5 historical analogies/)).toBeInTheDocument();
  });
});

// ── ContrarianCallout ─────────────────────────────────────────────────────────

describe('ContrarianCallout', () => {
  it('renders passed text with "History says" label', () => {
    render(<ContrarianCallout text="History shows commodity spikes." />);
    expect(screen.getByTestId('contrarian-callout')).toBeInTheDocument();
    expect(screen.getByText('History shows commodity spikes.')).toBeInTheDocument();
    expect(screen.getByText(/History says/i)).toBeInTheDocument();
  });

  it('has role=note', () => {
    render(<ContrarianCallout text="Test" />);
    expect(screen.getByRole('note')).toBeInTheDocument();
  });
});

// ── SidePanelAnalogies ────────────────────────────────────────────────────────

function buildAnalogy(id: string, score: number): AnalogSummary {
  return { event_id: id, headline: `Event ${id}`, occurred_at: '2020-01-01', similarity_score: score };
}

describe('SidePanelAnalogies', () => {
  it('renders exactly 3 entries for 3 analogies', () => {
    render(
      <SidePanelAnalogies analogies={[buildAnalogy('1', 0.9), buildAnalogy('2', 0.8), buildAnalogy('3', 0.7)]} />,
    );
    expect(screen.getAllByTestId(/^analogy-item-/)).toHaveLength(3);
  });

  it('renders "No historical analogies found" for empty array', () => {
    render(<SidePanelAnalogies analogies={[]} />);
    expect(screen.getByText('No historical analogies found.')).toBeInTheDocument();
  });

  it('displays similarity score 0.87 as "87%"', () => {
    render(<SidePanelAnalogies analogies={[buildAnalogy('1', 0.87)]} />);
    expect(screen.getByTestId('analogy-score-0')).toHaveTextContent('87%');
  });

  it('truncates headline to ≤80 chars', () => {
    render(
      <SidePanelAnalogies analogies={[buildAnalogy('1', 0.5)].map((a) => ({
        ...a,
        headline: 'A'.repeat(100),
      }))} />,
    );
    const el = screen.getByTestId('analogy-headline-0');
    expect(el.textContent!.length).toBeLessThanOrEqual(80);
  });
});

// ── AuditTrailView ────────────────────────────────────────────────────────────

function buildAuditTrailData(): AuditTrailData {
  return {
    event_id: 'evt-001',
    prompt_version: 'abc123def456',
    langfuse_trace_url: 'https://langfuse.example.com/traces/xyz',
    analogies: [
      { event_id: 'old-1', headline: 'Old event A', occurred_at: '2020-01-01', similarity_score: 0.92 },
    ],
    reasoning_steps: [
      { agent_role: 'event_classifier', step_index: 0, content: 'Classified', tool_calls: [] },
      { agent_role: 'recommendation_synthesizer', step_index: 1, content: 'Signal: WATCH', tool_calls: ['analogy_lookup'] },
    ],
  };
}

describe('AuditTrailView', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('does not render when isOpen=false', () => {
    render(
      <AuditTrailView eventId="evt-001" isOpen={false} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );
    expect(screen.queryByTestId('audit-trail-view')).not.toBeInTheDocument();
  });

  it('renders prompt SHA, reasoning steps, and Langfuse link when open', () => {
    jest.spyOn(useAuditTrailModule, 'useAuditTrail').mockReturnValue({
      data: buildAuditTrailData(),
      isLoading: false,
      isSuccess: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useAuditTrailModule.useAuditTrail>);

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('audit-prompt-version')).toHaveTextContent('abc123def456');
    expect(screen.getByTestId('reasoning-step-0')).toBeInTheDocument();
    expect(screen.getByTestId('reasoning-step-1')).toBeInTheDocument();
    const link = screen.getByTestId('langfuse-trace-link') as HTMLAnchorElement;
    expect(link.href).toContain('langfuse.example.com');
    expect(link.target).toBe('_blank');
  });

  it('omits Langfuse link when langfuse_trace_url is empty', () => {
    jest.spyOn(useAuditTrailModule, 'useAuditTrail').mockReturnValue({
      data: { ...buildAuditTrailData(), langfuse_trace_url: '' },
      isLoading: false,
      isSuccess: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useAuditTrailModule.useAuditTrail>);

    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.queryByTestId('langfuse-trace-link')).not.toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    jest.spyOn(useAuditTrailModule, 'useAuditTrail').mockReturnValue({
      data: buildAuditTrailData(),
      isLoading: false,
      isSuccess: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useAuditTrailModule.useAuditTrail>);

    const onClose = jest.fn();
    render(
      <AuditTrailView eventId="evt-001" isOpen={true} onClose={onClose} />,
      { wrapper: makeWrapper() },
    );

    fireEvent.click(screen.getByTestId('audit-trail-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
