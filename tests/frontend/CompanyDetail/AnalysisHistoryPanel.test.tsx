import { describe, it, expect } from 'vitest';
/**
 * Tests for AnalysisHistoryPanel component.
 *
 * Tests:
 * - Signal badge colors for different action signals
 * - Shows empty state when no history
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { AnalysisHistoryPanel } from '../../../src/frontend/pages/CompanyDetail/AnalysisHistoryPanel';
import type { AnalysisHistoryItem } from '../../../src/frontend/pages/CompanyDetail/types';

function makeHistoryItem(id: string, signal: string): AnalysisHistoryItem {
  return {
    rec_id: id,
    generated_at: '2024-02-01T00:00:00Z',
    workflow_type: 'on_demand',
    action_signal: signal,
    confidence: 0.85,
    rationale_summary: 'Strong fundamentals',
  };
}

describe('AnalysisHistoryPanel', () => {
  it('shows empty state when no history', () => {
    render(<AnalysisHistoryPanel history={[]} />);
    expect(screen.getByTestId('analysis-history-empty')).toBeInTheDocument();
  });

  it('renders signal badge with bullish class for BUY_OPP', () => {
    const history = [makeHistoryItem('r1', 'BUY_OPP')];
    render(<AnalysisHistoryPanel history={history} />);
    const badge = screen.getByTestId('signal-badge-r1');
    expect(badge.className).toContain('signal-badge--bullish');
  });

  it('renders signal badge with bearish class for REDUCE_RISK', () => {
    const history = [makeHistoryItem('r2', 'REDUCE_RISK')];
    render(<AnalysisHistoryPanel history={history} />);
    const badge = screen.getByTestId('signal-badge-r2');
    expect(badge.className).toContain('signal-badge--bearish');
  });

  it('renders signal badge with bearish class for HEDGE', () => {
    const history = [makeHistoryItem('r3', 'HEDGE')];
    render(<AnalysisHistoryPanel history={history} />);
    const badge = screen.getByTestId('signal-badge-r3');
    expect(badge.className).toContain('signal-badge--bearish');
  });

  it('renders signal badge with neutral class for HOLD', () => {
    const history = [makeHistoryItem('r4', 'HOLD')];
    render(<AnalysisHistoryPanel history={history} />);
    const badge = screen.getByTestId('signal-badge-r4');
    expect(badge.className).toContain('signal-badge--neutral');
  });

  it('renders signal badge with neutral class for WATCH', () => {
    const history = [makeHistoryItem('r5', 'WATCH')];
    render(<AnalysisHistoryPanel history={history} />);
    const badge = screen.getByTestId('signal-badge-r5');
    expect(badge.className).toContain('signal-badge--neutral');
  });

  it('renders signal badge with neutral class for CONTRARIAN', () => {
    const history = [makeHistoryItem('r6', 'CONTRARIAN')];
    render(<AnalysisHistoryPanel history={history} />);
    const badge = screen.getByTestId('signal-badge-r6');
    expect(badge.className).toContain('signal-badge--neutral');
  });

  it('renders rationale summary text', () => {
    const history = [makeHistoryItem('r7', 'BUY_OPP')];
    render(<AnalysisHistoryPanel history={history} />);
    expect(screen.getByText('Strong fundamentals')).toBeInTheDocument();
  });
});
