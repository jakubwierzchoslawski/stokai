/**
 * side-panel-expand.test.tsx — Integration tests: Expand click opens side panel.
 *
 * PLAN-F-020 TASK-013
 *
 * Tests:
 *  1. Clicking "Expand" opens side panel; sparklines + "Why this read?" visible.
 *  2. low_sample=true → disclaimer visible in side panel.
 *  3. social_posts non-null → "Triggering posts" section rendered.
 *
 * AC-002, AC-005
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { ProgressiveDisclosureProvider, useDisclosure } from '../../../src/frontend/features/progressive-disclosure/ProgressiveDisclosureProvider';
import * as disclosureApi from '../../../src/frontend/features/progressive-disclosure/api/disclosure.api';
import type { PopupData, SidePanelData } from '../../../src/frontend/features/progressive-disclosure/types/disclosure.types';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(ProgressiveDisclosureProvider, null, children),
      ),
    );
  return Wrapper;
}

function buildPopupData(): PopupData {
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
  };
}

function buildSidePanelData(overrides: Partial<SidePanelData> = {}): SidePanelData {
  return {
    ...buildPopupData(),
    summary: 'Event summary',
    sparklines: [
      { ticker: 'AAPL', ohlcv_7d: [{ ts: '2026-01-01', close: 150 }] },
    ],
    rationale: 'Rationale text',
    analogies: [
      { event_id: 'old-1', headline: 'Old event', occurred_at: '2020-01-01', similarity_score: 0.87 },
    ],
    affected_companies: [],
    is_contrarian: false,
    contrarian_callout: null,
    social_posts: null,
    audit_trail_url: '/events/evt-001/audit-trail',
    ...overrides,
  };
}

function MapStub() {
  const { openPopup } = useDisclosure();
  return (
    <button data-testid="trigger-popup" onClick={() => openPopup('evt-001')}>
      Trigger
    </button>
  );
}

describe('Side panel expand integration', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('Expand click opens side panel with sparklines and "Why this read?" link', async () => {
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(buildPopupData());
    jest.spyOn(disclosureApi, 'fetchSidePanelData').mockResolvedValue(buildSidePanelData());

    render(<MapStub />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('trigger-popup'));
    await waitFor(() => expect(screen.getByTestId('expand-button')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('expand-button'));

    await waitFor(() => {
      const panel = screen.getByTestId('side-panel');
      return panel.style.transform === 'translateX(0)';
    });

    await waitFor(() => expect(screen.getByTestId('sparklines-section')).toBeInTheDocument());
    expect(screen.getByTestId('why-this-read-link')).toBeInTheDocument();
    expect(screen.getByTestId('analogies-section')).toBeInTheDocument();
  });

  it('low_sample=true shows disclaimer in side panel', async () => {
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(buildPopupData());
    jest.spyOn(disclosureApi, 'fetchSidePanelData').mockResolvedValue(
      buildSidePanelData({ low_sample: true, sample_size: 3 }),
    );

    render(<MapStub />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('trigger-popup'));
    await waitFor(() => expect(screen.getByTestId('expand-button')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('expand-button'));

    await waitFor(() => expect(screen.getByTestId('low-sample-disclaimer')).toBeInTheDocument());
  });

  it('social_posts non-null shows "Triggering posts" section', async () => {
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(buildPopupData());
    jest.spyOn(disclosureApi, 'fetchSidePanelData').mockResolvedValue(
      buildSidePanelData({
        social_posts: [
          { post_id: 'p1', source: 'Twitter', text: 'Breaking news', timestamp: '2026-01-01T10:00:00Z' },
        ],
      }),
    );

    render(<MapStub />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('trigger-popup'));
    await waitFor(() => expect(screen.getByTestId('expand-button')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('expand-button'));

    await waitFor(() => expect(screen.getByTestId('social-posts-section')).toBeInTheDocument());
    expect(screen.getByText('Breaking news')).toBeInTheDocument();
  });
});
