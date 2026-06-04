/**
 * audit-trail.test.tsx — Integration tests: "Why this read?" opens audit trail.
 *
 * PLAN-F-020 TASK-013
 *
 * Tests:
 *  - Clicking "Why this read?" opens audit trail overlay with SHA, reasoning steps, Langfuse link.
 *
 * AC-003
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { ProgressiveDisclosureProvider, useDisclosure } from '../../../src/frontend/features/progressive-disclosure/ProgressiveDisclosureProvider';
import * as disclosureApi from '../../../src/frontend/features/progressive-disclosure/api/disclosure.api';
import type { PopupData, SidePanelData, AuditTrailData } from '../../../src/frontend/features/progressive-disclosure/types/disclosure.types';

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
    intensity: 3,
    headline: 'Test event',
    time_ago: '5 minutes ago',
    location: 'Middle East',
    exposed_holdings_count: 2,
    tickers_with_delta: [],
    action_signal: 'WATCH',
    confidence: 0.75,
    sample_size: 8,
    low_sample: false,
  };
}

function buildSidePanelData(): SidePanelData {
  return {
    ...buildPopupData(),
    summary: 'Summary',
    sparklines: [],
    rationale: 'Rationale',
    analogies: [],
    affected_companies: [],
    is_contrarian: false,
    contrarian_callout: null,
    social_posts: null,
    audit_trail_url: '/events/evt-001/audit-trail',
  };
}

function buildAuditTrailData(): AuditTrailData {
  return {
    event_id: 'evt-001',
    prompt_version: 'sha256abc123',
    langfuse_trace_url: 'https://langfuse.example.com/traces/xyz',
    analogies: [],
    reasoning_steps: [
      { agent_role: 'event_classifier', step_index: 0, content: 'Classified', tool_calls: [] },
      { agent_role: 'recommendation_synthesizer', step_index: 1, content: 'Signal: WATCH', tool_calls: ['analogy_lookup'] },
    ],
  };
}

describe('Audit trail integration', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('clicking "Why this read?" opens audit trail with SHA, steps, and Langfuse link', async () => {
    jest.spyOn(disclosureApi, 'fetchPopupData').mockResolvedValue(buildPopupData());
    jest.spyOn(disclosureApi, 'fetchSidePanelData').mockResolvedValue(buildSidePanelData());
    jest.spyOn(disclosureApi, 'fetchAuditTrail').mockResolvedValue(buildAuditTrailData());

    render(<MapStub />, { wrapper: makeWrapper() });

    // Open popup
    fireEvent.click(screen.getByTestId('trigger-popup'));
    await waitFor(() => expect(screen.getByTestId('expand-button')).toBeInTheDocument());

    // Expand to side panel
    fireEvent.click(screen.getByTestId('expand-button'));
    await waitFor(() => expect(screen.getByTestId('why-this-read-link')).toBeInTheDocument());

    // Click "Why this read?"
    fireEvent.click(screen.getByTestId('why-this-read-link'));

    // Audit trail overlay appears
    await waitFor(() => expect(screen.getByTestId('audit-trail-view')).toBeInTheDocument());

    // Verify SHA displayed
    expect(screen.getByTestId('audit-prompt-version')).toHaveTextContent('sha256abc123');

    // Verify 2 reasoning steps
    expect(screen.getByTestId('reasoning-step-0')).toBeInTheDocument();
    expect(screen.getByTestId('reasoning-step-1')).toBeInTheDocument();

    // Verify Langfuse link
    const langfuseLink = screen.getByTestId('langfuse-trace-link') as HTMLAnchorElement;
    expect(langfuseLink.href).toContain('langfuse.example.com');
  });
});
