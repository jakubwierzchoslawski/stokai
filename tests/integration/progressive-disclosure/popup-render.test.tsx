/**
 * popup-render.test.tsx — Integration tests: popup renders with correct data.
 *
 * PLAN-F-020 TASK-013
 *
 * Tests:
 *  1. Popup renders with all required fields; side panel not visible.
 *  2. Low-sample disclaimer shown when low_sample=true in popup data.
 *
 * Uses React Testing Library. API calls are mocked via jest.spyOn on the
 * disclosure.api module (MSW not installed; patterns follow existing test suite).
 *
 * AC-001, AC-005
 */

import React from 'react';
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { ProgressiveDisclosureProvider, useDisclosure } from '../../../src/frontend/features/progressive-disclosure/ProgressiveDisclosureProvider';
import * as disclosureApi from '../../../src/frontend/features/progressive-disclosure/api/disclosure.api';
import type { PopupData, SidePanelData } from '../../../src/frontend/features/progressive-disclosure/types/disclosure.types';

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function buildPopupData(overrides: Partial<PopupData> = {}): PopupData {
  return {
    event_id: 'evt-001',
    category: ['GEOPOLITICAL'],
    intensity: 3,
    headline: 'Integration test event',
    time_ago: '5 minutes ago',
    location: 'Middle East',
    exposed_holdings_count: 3,
    tickers_with_delta: [
      { ticker: 'AAPL', score_delta: 2.1 },
      { ticker: 'XOM', score_delta: -1.3 },
    ],
    action_signal: 'WATCH',
    confidence: 0.8,
    sample_size: 7,
    low_sample: false,
    ...overrides,
  };
}

// Trigger button that calls openPopup
function MapStub() {
  const { openPopup } = useDisclosure();
  return (
    <button
      data-testid="trigger-popup"
      onClick={() => openPopup('evt-001')}
    >
      Click Map Pulse
    </button>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Popup render integration', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('popup renders with all required fields; side panel not visible; no disclaimer', async () => {
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(buildPopupData({ low_sample: false }));
    // Side panel data: prevent side panel from fetching
    jest.spyOn(disclosureApi, 'fetchSidePanelData').mockResolvedValue({} as SidePanelData);

    render(<MapStub />, { wrapper: makeWrapper() });

    // Trigger popup
    fireEvent.click(screen.getByTestId('trigger-popup'));

    // Popup content arrives
    await waitFor(() => expect(screen.getByTestId('event-popup')).toBeInTheDocument());

    expect(screen.getByTestId('category')).toHaveTextContent('GEOPOLITICAL');
    expect(screen.getByTestId('intensity-badge')).toHaveTextContent('3');
    expect(screen.getByTestId('headline')).toHaveTextContent('Integration test event');
    expect(screen.getByTestId('exposed-holdings-count')).toHaveTextContent('3');
    expect(screen.getByTestId('ticker-AAPL')).toBeInTheDocument();
    expect(screen.getByTestId('action-signal')).toHaveTextContent('WATCH');
    expect(screen.getByTestId('confidence')).toHaveTextContent('80%');

    // Side panel should NOT be visible
    const sidePanel = screen.getByTestId('side-panel');
    expect(sidePanel.style.transform).toContain('translateX(100%)');

    // No disclaimer
    expect(screen.queryByTestId('low-sample-disclaimer')).not.toBeInTheDocument();
  });

  it('popup shows low-sample disclaimer when low_sample=true', async () => {
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(
      buildPopupData({ low_sample: true, sample_size: 3 }),
    );

    render(<MapStub />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('trigger-popup'));

    await waitFor(() => expect(screen.getByTestId('event-popup')).toBeInTheDocument());

    expect(screen.getByTestId('low-sample-disclaimer')).toBeInTheDocument();
    expect(screen.getByText(/fewer than 5 historical analogies/)).toBeInTheDocument();
  });
});
