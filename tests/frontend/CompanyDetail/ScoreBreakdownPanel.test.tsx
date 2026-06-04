/**
 * Tests for ScoreBreakdownPanel component.
 *
 * Tests:
 * - Renders one card per score item
 * - Shows empty state when no scores
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { ScoreBreakdownPanel } from '../../../src/frontend/pages/CompanyDetail/ScoreBreakdownPanel';
import type { ScoreBreakdownItem } from '../../../src/frontend/pages/CompanyDetail/types';

function makeScore(i: number): ScoreBreakdownItem {
  return {
    indicator_id: `indicator-${i}`,
    indicator_name: `Indicator ${i}`,
    formula_summary: `formula_${i}`,
    weight: 0.25,
    raw_value: i * 1.0,
    score: i * 10.0,
    geo_adjusted: null,
    sub_score_contribution: (i * 10.0 * 0.25) / 100,
    sparkline: [10, 20, 30],
  };
}

describe('ScoreBreakdownPanel', () => {
  it('renders one card per score item', () => {
    const scores = [makeScore(1), makeScore(2), makeScore(3)];
    render(<ScoreBreakdownPanel scores={scores} />);

    const cards = screen.getAllByRole('article');
    expect(cards).toHaveLength(3);
  });

  it('renders the indicator name for each card', () => {
    const scores = [makeScore(1), makeScore(2)];
    render(<ScoreBreakdownPanel scores={scores} />);

    expect(screen.getByText('Indicator 1')).toBeInTheDocument();
    expect(screen.getByText('Indicator 2')).toBeInTheDocument();
  });

  it('shows empty state when no scores', () => {
    render(<ScoreBreakdownPanel scores={[]} />);
    expect(screen.getByTestId('score-breakdown-empty')).toBeInTheDocument();
  });

  it('renders formula summary for each card', () => {
    const scores = [makeScore(1)];
    render(<ScoreBreakdownPanel scores={scores} />);
    expect(screen.getByText('formula_1')).toBeInTheDocument();
  });
});
