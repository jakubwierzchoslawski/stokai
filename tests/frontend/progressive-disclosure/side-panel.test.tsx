/**
 * side-panel.test.tsx — Tests for SidePanel component.
 *
 * PLAN-F-020 TASK-009 (TDD)
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { SidePanel } from '../../../src/frontend/features/progressive-disclosure/components/SidePanel';
import * as useSidePanelDataModule from '../../../src/frontend/features/progressive-disclosure/hooks/useSidePanelData';
import type { SidePanelData } from '../../../src/frontend/features/progressive-disclosure/types/disclosure.types';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function buildSidePanelData(overrides: Partial<SidePanelData> = {}): SidePanelData {
  return {
    event_id: 'evt-001',
    category: ['GEOPOLITICAL'],
    intensity: 3,
    headline: 'Test event',
    time_ago: '5 minutes ago',
    location: 'Middle East',
    exposed_holdings_count: 2,
    tickers_with_delta: [{ ticker: 'AAPL', score_delta: 1.5 }],
    action_signal: 'WATCH',
    confidence: 0.75,
    sample_size: 8,
    low_sample: false,
    summary: 'Event summary text',
    sparklines: [
      { ticker: 'AAPL', ohlcv_7d: [{ ts: '2026-01-01', close: 150 }, { ts: '2026-01-02', close: 155 }] },
    ],
    rationale: 'Rationale text',
    analogies: [
      { event_id: 'old-evt-1', headline: 'Old event', occurred_at: '2020-01-01', similarity_score: 0.87 },
    ],
    affected_companies: [
      { company_id: 'comp-1', ticker: 'AAPL', name: 'Apple Inc', score: 72, delta: 1.5 },
    ],
    is_contrarian: false,
    contrarian_callout: null,
    social_posts: null,
    audit_trail_url: '/events/evt-001/audit-trail',
    ...overrides,
  };
}

function mockUseSidePanelData(opts: { isLoading?: boolean; data?: SidePanelData }) {
  jest.spyOn(useSidePanelDataModule, 'useSidePanelData').mockReturnValue({
    data: opts.data,
    isLoading: opts.isLoading ?? false,
    isSuccess: !opts.isLoading && !!opts.data,
    isError: false,
    error: null,
  } as ReturnType<typeof useSidePanelDataModule.useSidePanelData>);
}

describe('SidePanel', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('is off-screen when isOpen=false', () => {
    jest.spyOn(useSidePanelDataModule, 'useSidePanelData').mockReturnValue({
      data: undefined,
      isLoading: false,
      isSuccess: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useSidePanelDataModule.useSidePanelData>);

    render(
      <SidePanel eventId="evt-001" isOpen={false} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    const panel = screen.getByTestId('side-panel');
    expect(panel.style.transform).toContain('translateX(100%)');
    expect(screen.queryByTestId('side-panel-summary')).not.toBeInTheDocument();
  });

  it('renders all required content sections when isOpen=true', () => {
    mockUseSidePanelData({ data: buildSidePanelData() });

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('side-panel-summary')).toHaveTextContent('Event summary text');
    expect(screen.getByTestId('sparklines-section')).toBeInTheDocument();
    expect(screen.getByTestId('side-panel-action-signal')).toHaveTextContent('WATCH');
    expect(screen.getByTestId('side-panel-rationale')).toHaveTextContent('Rationale text');
    expect(screen.getByTestId('analogies-section')).toBeInTheDocument();
    expect(screen.getByTestId('affected-companies-section')).toBeInTheDocument();
  });

  it('renders ContrarianCallout before action signal when is_contrarian=true', () => {
    mockUseSidePanelData({
      data: buildSidePanelData({
        is_contrarian: true,
        contrarian_callout: 'History shows commodity spikes.',
      }),
    });

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('contrarian-callout')).toBeInTheDocument();
    expect(screen.getByText('History shows commodity spikes.')).toBeInTheDocument();

    const panel = screen.getByTestId('side-panel');
    const allElements = Array.from(panel.querySelectorAll('[data-testid]'));
    const calloutIdx = allElements.indexOf(screen.getByTestId('contrarian-callout'));
    const signalIdx = allElements.indexOf(screen.getByTestId('side-panel-action-signal'));
    expect(calloutIdx).toBeLessThan(signalIdx);
  });

  it('does not render ContrarianCallout when is_contrarian=false', () => {
    mockUseSidePanelData({ data: buildSidePanelData({ is_contrarian: false }) });

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.queryByTestId('contrarian-callout')).not.toBeInTheDocument();
  });

  it('shows LowSampleDisclaimer when low_sample=true', () => {
    mockUseSidePanelData({ data: buildSidePanelData({ low_sample: true }) });

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('low-sample-disclaimer')).toBeInTheDocument();
  });

  it('renders Triggering posts when social_posts is non-empty', () => {
    mockUseSidePanelData({
      data: buildSidePanelData({
        social_posts: [{ post_id: 'p1', source: 'Twitter', text: 'Breaking news', timestamp: '2026-01-01T10:00:00Z' }],
      }),
    });

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('social-posts-section')).toBeInTheDocument();
    expect(screen.getByText('Breaking news')).toBeInTheDocument();
  });

  it('social_posts null → no Triggering posts section', () => {
    mockUseSidePanelData({ data: buildSidePanelData({ social_posts: null }) });

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.queryByTestId('social-posts-section')).not.toBeInTheDocument();
  });

  it('calls onOpenAuditTrail when "Why this read?" is clicked', () => {
    mockUseSidePanelData({ data: buildSidePanelData() });
    const onOpenAuditTrail = jest.fn();

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={onOpenAuditTrail} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    fireEvent.click(screen.getByTestId('why-this-read-link'));
    expect(onOpenAuditTrail).toHaveBeenCalledTimes(1);
  });

  it('calls onOpenDeepDive when "Full Analysis" is clicked', () => {
    mockUseSidePanelData({ data: buildSidePanelData() });
    const onOpenDeepDive = jest.fn();

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={jest.fn()} onOpenAuditTrail={jest.fn()} onOpenDeepDive={onOpenDeepDive} />,
      { wrapper: makeWrapper() },
    );

    fireEvent.click(screen.getByTestId('full-analysis-button'));
    expect(onOpenDeepDive).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when close button is clicked', () => {
    mockUseSidePanelData({ data: buildSidePanelData() });
    const onClose = jest.fn();

    render(
      <SidePanel eventId="evt-001" isOpen={true} onClose={onClose} onOpenAuditTrail={jest.fn()} onOpenDeepDive={jest.fn()} />,
      { wrapper: makeWrapper() },
    );

    fireEvent.click(screen.getByTestId('side-panel-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
