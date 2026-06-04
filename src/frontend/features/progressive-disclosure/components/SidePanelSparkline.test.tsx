/**
 * SidePanelSparkline.test.tsx — TDD tests for SidePanelSparkline component.
 *
 * PLAN-F-020 TASK-008
 */

import React from 'react';
import { render, screen } from '@testing-library/react';

import { SidePanelSparkline } from './SidePanelSparkline';
import type { SparklinePoint } from '../types/disclosure.types';

function buildPoints(closes: number[]): SparklinePoint[] {
  return closes.map((close, i) => ({
    ts: `2026-01-0${i + 1}`,
    close,
  }));
}

describe('SidePanelSparkline', () => {
  it('renders a chart element (role=img) for 7 data points', () => {
    const points = buildPoints([100, 102, 101, 104, 103, 106, 105]);
    render(<SidePanelSparkline ticker="AAPL" ohlcv_7d={points} />);
    expect(screen.getByRole('img', { name: /AAPL price sparkline/ })).toBeInTheDocument();
  });

  it('renders "No price data" placeholder when ohlcv_7d is empty', () => {
    render(<SidePanelSparkline ticker="AAPL" ohlcv_7d={[]} />);
    expect(screen.getByText('No price data')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('displays the ticker label', () => {
    const points = buildPoints([100, 105]);
    render(<SidePanelSparkline ticker="MSFT" ohlcv_7d={points} />);
    expect(screen.getByText('MSFT')).toBeInTheDocument();
  });

  it('has testid for external reference', () => {
    const points = buildPoints([100, 105]);
    render(<SidePanelSparkline ticker="AAPL" ohlcv_7d={points} />);
    expect(screen.getByTestId('sparkline-AAPL')).toBeInTheDocument();
  });
});
