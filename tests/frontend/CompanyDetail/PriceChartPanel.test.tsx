/**
 * Tests for PriceChartPanel component.
 *
 * Tests:
 * - Renders with empty bars (no crash)
 * - Shows empty state message when no data
 * - Shows loading state
 * - Renders chart container when data is provided
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { PriceChartPanel } from '../../../src/frontend/pages/CompanyDetail/PriceChartPanel';
import type { PriceBar } from '../../../src/frontend/pages/CompanyDetail/types';

// Mock Recharts to avoid canvas rendering issues in jsdom
jest.mock('recharts', () => {
  const MockChart = ({ children, 'data-testid': testId }: { children?: React.ReactNode; 'data-testid'?: string }) =>
    React.createElement('div', { 'data-testid': testId ?? 'recharts-chart' }, children);
  return {
    ComposedChart: MockChart,
    Line: () => null,
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) =>
      React.createElement('div', { 'data-testid': 'responsive-container' }, children),
    Legend: () => null,
  };
});

function makeBar(offset: number): PriceBar {
  return {
    company_id: 'c1c1c1c1-0000-0000-0000-000000000001',
    ts: `2024-01-${String(offset + 1).padStart(2, '0')}T00:00:00Z`,
    open: 100 + offset,
    high: 110 + offset,
    low: 90 + offset,
    close: 105 + offset,
    volume: 1_000_000,
    interval: '1d',
  };
}

describe('PriceChartPanel', () => {
  it('renders without crashing when bars is empty', () => {
    render(<PriceChartPanel bars={[]} />);
    expect(screen.getByTestId('price-chart-empty')).toBeInTheDocument();
  });

  it('shows empty state message when no data', () => {
    render(<PriceChartPanel bars={[]} />);
    expect(screen.getByText('No price data available.')).toBeInTheDocument();
  });

  it('shows loading state when isLoading is true', () => {
    render(<PriceChartPanel bars={[]} isLoading={true} />);
    expect(screen.getByTestId('price-chart-loading')).toBeInTheDocument();
    expect(screen.getByText('Loading price data...')).toBeInTheDocument();
  });

  it('renders chart container when bars are provided', () => {
    const bars = [makeBar(0), makeBar(1), makeBar(2)];
    render(<PriceChartPanel bars={bars} />);
    expect(screen.getByTestId('price-chart-panel')).toBeInTheDocument();
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
  });
});
