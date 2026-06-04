/**
 * DeepDivePage.test.tsx — TDD tests for DeepDivePage component.
 *
 * PLAN-F-020 TASK-011
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { DeepDivePage } from './DeepDivePage';
import * as useDeepDiveModule from '../hooks/useDeepDive';
import type { DeepDiveData, DeepDivePending } from '../types/disclosure.types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeWrapper(eventId: string = 'evt-001') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(
        MemoryRouter,
        { initialEntries: [`/events/${eventId}/deep-dive`] },
        React.createElement(
          Routes,
          null,
          React.createElement(Route, { path: '/events/:eventId/deep-dive', element: children }),
        ),
      ),
    );
  return Wrapper;
}

function buildDeepDiveData(overrides: Partial<DeepDiveData> = {}): DeepDiveData {
  return {
    event_id: 'evt-001',
    memo: 'Full analysis memo text.',
    scenario_tree: null,
    analogies: [
      { event_id: 'old-1', headline: 'Analog A', occurred_at: '2020-01-01', similarity_score: 0.9 },
      { event_id: 'old-2', headline: 'Analog B', occurred_at: '2019-06-15', similarity_score: 0.7 },
    ],
    affected_companies: [
      { company_id: 'comp-1', ticker: 'AAPL', name: 'Apple Inc', score: 72, delta: 1.5 },
      { company_id: 'comp-2', ticker: 'MSFT', name: 'Microsoft', score: 65, delta: -0.5 },
    ],
    generated_at: new Date().toISOString(),
    ...overrides,
  };
}

function mockUseDeepDive(opts: {
  isLoading?: boolean;
  data?: DeepDiveData | DeepDivePending;
}) {
  jest.spyOn(useDeepDiveModule, 'useDeepDive').mockReturnValue({
    data: opts.data,
    isLoading: opts.isLoading ?? false,
    isSuccess: !opts.isLoading && !!opts.data,
    isError: false,
    error: null,
    pollCount: 0,
  } as ReturnType<typeof useDeepDiveModule.useDeepDive>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DeepDivePage', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('shows loading message when status is pending', () => {
    const pending: DeepDivePending = { status: 'pending' };
    mockUseDeepDive({ data: pending });

    render(<DeepDivePage />, { wrapper: makeWrapper() });

    expect(screen.getByTestId('deep-dive-loading')).toBeInTheDocument();
    expect(screen.getByTestId('deep-dive-loading-text')).toHaveTextContent(
      'Generating deep-dive analysis',
    );
  });

  it('shows loading message when isLoading=true', () => {
    mockUseDeepDive({ isLoading: true });

    render(<DeepDivePage />, { wrapper: makeWrapper() });

    expect(screen.getByTestId('deep-dive-loading')).toBeInTheDocument();
  });

  it('renders memo text and affected companies table on success', () => {
    mockUseDeepDive({ data: buildDeepDiveData() });

    render(<DeepDivePage />, { wrapper: makeWrapper() });

    expect(screen.getByTestId('deep-dive-page')).toBeInTheDocument();
    expect(screen.getByTestId('deep-dive-memo')).toHaveTextContent('Full analysis memo text.');
    expect(screen.getAllByTestId(/^company-row-/)).toHaveLength(2);
  });

  it('renders "No scenario analysis available" when scenario_tree is null', () => {
    mockUseDeepDive({ data: buildDeepDiveData({ scenario_tree: null }) });

    render(<DeepDivePage />, { wrapper: makeWrapper() });

    expect(screen.getByTestId('no-scenario-analysis')).toBeInTheDocument();
    expect(screen.getByText('No scenario analysis available.')).toBeInTheDocument();
  });

  it('renders collapsible tree when scenario_tree has children', () => {
    mockUseDeepDive({
      data: buildDeepDiveData({
        scenario_tree: {
          label: 'Base case',
          probability: 0.6,
          description: 'Most likely outcome',
          children: [
            {
              label: 'Bullish variant',
              probability: 0.3,
              description: 'Higher commodity prices',
              children: [],
            },
          ],
        },
      }),
    });

    render(<DeepDivePage />, { wrapper: makeWrapper() });

    expect(screen.getByText('Base case')).toBeInTheDocument();
    expect(screen.getByText('Bullish variant')).toBeInTheDocument();
  });

  it('analogies table changes order when sort header is clicked', () => {
    mockUseDeepDive({ data: buildDeepDiveData() });

    render(<DeepDivePage />, { wrapper: makeWrapper() });

    const rows = screen.getAllByTestId(/^analogy-row-/);
    const firstHeadlineBefore = rows[0].querySelectorAll('td')[0].textContent;

    // Click sort by score (toggles ascending)
    fireEvent.click(screen.getByTestId('sort-by-score'));

    const rowsAfter = screen.getAllByTestId(/^analogy-row-/);
    const firstHeadlineAfter = rowsAfter[0].querySelectorAll('td')[0].textContent;

    // After toggling the sort order should change
    expect(firstHeadlineAfter).not.toBe(firstHeadlineBefore);
  });

  it('renders back link with href="/"', () => {
    mockUseDeepDive({ data: buildDeepDiveData() });

    render(<DeepDivePage />, { wrapper: makeWrapper() });

    const backLink = screen.getByTestId('back-to-map-link') as HTMLAnchorElement;
    expect(backLink).toBeInTheDocument();
    // react-router-dom Link renders with href attribute
    expect(backLink.getAttribute('href')).toBe('/');
  });
});
