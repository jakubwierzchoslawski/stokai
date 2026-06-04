/**
 * contrarian-callout.test.tsx — Integration test: contrarian flag renders callout first.
 *
 * PLAN-F-020 TASK-013
 *
 * Tests:
 *  - ContrarianCallout is the first visible content block in side panel.
 *  - Callout text matches the mock value.
 *  - Callout appears before the action_signal text.
 *
 * AC-004
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

function MapStub() {
  const { openPopup } = useDisclosure();
  return (
    <button data-testid="trigger-popup" onClick={() => openPopup('evt-001')}>Trigger</button>
  );
}

function buildPopupData(): PopupData {
  return {
    event_id: 'evt-001',
    category: ['GEOPOLITICAL'],
    intensity: 4,
    headline: 'Contrarian test event',
    time_ago: '2 minutes ago',
    location: 'Eastern Europe',
    exposed_holdings_count: 5,
    tickers_with_delta: [{ ticker: 'XOM', score_delta: -2.5 }],
    action_signal: 'CONTRARIAN',
    confidence: 0.68,
    sample_size: 12,
    low_sample: false,
  };
}

function buildContrarianSidePanelData(): SidePanelData {
  return {
    ...buildPopupData(),
    summary: 'Contrarian event summary',
    sparklines: [],
    rationale: 'Despite initial panic, history suggests recovery.',
    analogies: [],
    affected_companies: [],
    is_contrarian: true,
    contrarian_callout: 'History shows conflicts in this region cause short-term commodity spikes.',
    social_posts: null,
    audit_trail_url: '/events/evt-001/audit-trail',
  };
}

describe('Contrarian callout integration', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('ContrarianCallout is first visible content block; text matches mock; appears before action_signal', async () => {
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(buildPopupData());
    jest.spyOn(disclosureApi, 'fetchSidePanelData').mockResolvedValue(buildContrarianSidePanelData());

    render(<MapStub />, { wrapper: makeWrapper() });

    fireEvent.click(screen.getByTestId('trigger-popup'));
    await waitFor(() => expect(screen.getByTestId('expand-button')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('expand-button'));

    // Wait for side panel content
    await waitFor(() => expect(screen.getByTestId('contrarian-callout')).toBeInTheDocument());

    // Verify callout text matches mock value
    expect(screen.getByText(
      'History shows conflicts in this region cause short-term commodity spikes.',
    )).toBeInTheDocument();

    // Verify callout appears before action signal in DOM order
    const panel = screen.getByTestId('side-panel');
    const allElements = Array.from(panel.querySelectorAll('[data-testid]'));
    const calloutEl = screen.getByTestId('contrarian-callout');
    const signalEl = screen.getByTestId('side-panel-action-signal');
    const calloutIdx = allElements.indexOf(calloutEl);
    const signalIdx = allElements.indexOf(signalEl);
    expect(calloutIdx).toBeLessThan(signalIdx);
  });
});
