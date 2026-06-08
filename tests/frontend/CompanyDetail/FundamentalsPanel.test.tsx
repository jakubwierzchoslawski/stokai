import { describe, it, expect } from 'vitest';
/**
 * Tests for FundamentalsPanel component.
 *
 * Tests:
 * - Renders "â€”" for null values
 * - Renders numeric values when present
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { FundamentalsPanel } from '../../../src/frontend/pages/CompanyDetail/FundamentalsPanel';
import type { FundamentalsPanel as FundamentalsPanelData } from '../../../src/frontend/pages/CompanyDetail/types';

function makeFundamentals(overrides: Partial<FundamentalsPanelData> = {}): FundamentalsPanelData {
  return {
    pe_ratio: 20.5,
    eps: 3.14,
    revenue: 1_000_000,
    debt_to_equity: 0.5,
    source: 'fmp',
    as_of: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('FundamentalsPanel', () => {
  it('renders "â€”" for null pe_ratio', () => {
    render(<FundamentalsPanel fundamentals={makeFundamentals({ pe_ratio: null })} />);
    expect(screen.getByTestId('pe-ratio')).toHaveTextContent('â€”');
  });

  it('renders "â€”" for null eps', () => {
    render(<FundamentalsPanel fundamentals={makeFundamentals({ eps: null })} />);
    expect(screen.getByTestId('eps')).toHaveTextContent('â€”');
  });

  it('renders "â€”" for null revenue', () => {
    render(<FundamentalsPanel fundamentals={makeFundamentals({ revenue: null })} />);
    expect(screen.getByTestId('revenue')).toHaveTextContent('â€”');
  });

  it('renders "â€”" for null debt_to_equity', () => {
    render(<FundamentalsPanel fundamentals={makeFundamentals({ debt_to_equity: null })} />);
    expect(screen.getByTestId('debt-to-equity')).toHaveTextContent('â€”');
  });

  it('renders numeric pe_ratio when present', () => {
    render(<FundamentalsPanel fundamentals={makeFundamentals({ pe_ratio: 25.5 })} />);
    expect(screen.getByTestId('pe-ratio')).toHaveTextContent('25.5');
  });

  it('renders revenue with $ prefix when present', () => {
    render(<FundamentalsPanel fundamentals={makeFundamentals({ revenue: 1000000 })} />);
    expect(screen.getByTestId('revenue').textContent).toContain('$');
  });

  it('renders source and as_of', () => {
    render(<FundamentalsPanel fundamentals={makeFundamentals()} />);
    expect(screen.getByTestId('source')).toHaveTextContent('fmp');
    expect(screen.getByTestId('as-of')).not.toBeEmptyDOMElement();
  });
});
