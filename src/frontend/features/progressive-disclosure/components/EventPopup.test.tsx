import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * EventPopup.test.tsx â€” TDD tests for EventPopup component.
 *
 * PLAN-F-020 TASK-006
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { EventPopup } from './EventPopup';
import * as usePopupDataModule from '../hooks/usePopupData';
import type { PopupData } from '../types/disclosure.types';

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function buildPopupData(overrides: Partial<PopupData> = {}): PopupData {
  return {
    event_id: 'evt-001',
    category: ['GEOPOLITICAL'],
    intensity: 3,
    headline: 'Test event headline',
    time_ago: '5 minutes ago',
    location: 'Middle East',
    exposed_holdings_count: 4,
    tickers_with_delta: [
      { ticker: 'AAPL', score_delta: 2.5 },
      { ticker: 'MSFT', score_delta: -1.0 },
    ],
    action_signal: 'WATCH',
    confidence: 0.75,
    sample_size: 8,
    low_sample: false,
    ...overrides,
  };
}

function mockUsePopupData(overrides: {
  isLoading?: boolean;
  data?: PopupData;
}) {
  vi.spyOn(usePopupDataModule, 'usePopupData').mockReturnValue({
    data: overrides.data,
    isLoading: overrides.isLoading ?? false,
    isSuccess: !overrides.isLoading && !!overrides.data,
    isError: false,
    error: null,
  } as ReturnType<typeof usePopupDataModule.usePopupData>);
}

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('EventPopup', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders skeleton while isLoading=true', () => {
    mockUsePopupData({ isLoading: true });

    render(
      <EventPopup eventId="evt-001" onExpand={vi.fn()} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('popup-skeleton')).toBeInTheDocument();
    expect(screen.queryByTestId('event-popup')).not.toBeInTheDocument();
  });

  it('renders all required fields when data is available', () => {
    mockUsePopupData({ data: buildPopupData() });

    render(
      <EventPopup eventId="evt-001" onExpand={vi.fn()} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('event-popup')).toBeInTheDocument();
    expect(screen.getByTestId('category')).toHaveTextContent('GEOPOLITICAL');
    expect(screen.getByTestId('intensity-badge')).toHaveTextContent('3');
    expect(screen.getByTestId('headline')).toHaveTextContent('Test event headline');
    expect(screen.getByTestId('time-ago')).toHaveTextContent('5 minutes ago');
    expect(screen.getByTestId('location')).toHaveTextContent('Middle East');
    expect(screen.getByTestId('exposed-holdings-count')).toHaveTextContent('4');
    expect(screen.getByTestId('action-signal')).toHaveTextContent('WATCH');
    expect(screen.getByTestId('confidence')).toHaveTextContent('75%');
  });

  it('renders positive delta with "+" prefix', () => {
    mockUsePopupData({ data: buildPopupData() });

    render(
      <EventPopup eventId="evt-001" onExpand={vi.fn()} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    const aaplTicker = screen.getByTestId('ticker-AAPL');
    expect(aaplTicker).toHaveTextContent('+2.5');
  });

  it('renders negative delta with "â’" prefix', () => {
    mockUsePopupData({ data: buildPopupData() });

    render(
      <EventPopup eventId="evt-001" onExpand={vi.fn()} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    const msftTicker = screen.getByTestId('ticker-MSFT');
    expect(msftTicker).toHaveTextContent('â’1.0');
  });

  it('shows LowSampleDisclaimer when low_sample=true', () => {
    mockUsePopupData({ data: buildPopupData({ low_sample: true }) });

    render(
      <EventPopup eventId="evt-001" onExpand={vi.fn()} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.getByTestId('low-sample-disclaimer')).toBeInTheDocument();
  });

  it('does not show LowSampleDisclaimer when low_sample=false', () => {
    mockUsePopupData({ data: buildPopupData({ low_sample: false }) });

    render(
      <EventPopup eventId="evt-001" onExpand={vi.fn()} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    expect(screen.queryByTestId('low-sample-disclaimer')).not.toBeInTheDocument();
  });

  it('calls onExpand exactly once when Expand is clicked', () => {
    mockUsePopupData({ data: buildPopupData() });
    const onExpand = vi.fn();

    render(
      <EventPopup eventId="evt-001" onExpand={onExpand} onClose={vi.fn()} />,
      { wrapper: makeWrapper() },
    );

    fireEvent.click(screen.getByTestId('expand-button'));
    expect(onExpand).toHaveBeenCalledTimes(1);
  });

  it('calls onClose exactly once when close button is clicked', () => {
    mockUsePopupData({ data: buildPopupData() });
    const onClose = vi.fn();

    render(
      <EventPopup eventId="evt-001" onExpand={vi.fn()} onClose={onClose} />,
      { wrapper: makeWrapper() },
    );

    fireEvent.click(screen.getByTestId('close-button'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
