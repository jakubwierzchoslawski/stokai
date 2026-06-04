/**
 * SidePanelAnalogies.test.tsx — TDD tests for SidePanelAnalogies component.
 *
 * PLAN-F-020 TASK-008
 */

import React from 'react';
import { render, screen } from '@testing-library/react';

import { SidePanelAnalogies } from './SidePanelAnalogies';
import type { AnalogSummary } from '../types/disclosure.types';

function buildAnalogy(overrides: Partial<AnalogSummary> = {}): AnalogSummary {
  return {
    event_id: 'old-evt-001',
    headline: 'Historical event headline',
    occurred_at: '2020-03-15T00:00:00Z',
    similarity_score: 0.87,
    ...overrides,
  };
}

describe('SidePanelAnalogies', () => {
  it('renders exactly 3 list entries when 3 analogies provided', () => {
    const analogies = [
      buildAnalogy({ event_id: '1', similarity_score: 0.9 }),
      buildAnalogy({ event_id: '2', similarity_score: 0.8 }),
      buildAnalogy({ event_id: '3', similarity_score: 0.7 }),
    ];
    render(<SidePanelAnalogies analogies={analogies} />);
    expect(screen.getAllByTestId(/^analogy-item-/)).toHaveLength(3);
  });

  it('renders "No historical analogies found" when analogies is empty', () => {
    render(<SidePanelAnalogies analogies={[]} />);
    expect(screen.getByTestId('analogies-empty')).toBeInTheDocument();
    expect(screen.getByText('No historical analogies found.')).toBeInTheDocument();
  });

  it('displays similarity_score=0.87 as "87%"', () => {
    render(<SidePanelAnalogies analogies={[buildAnalogy({ similarity_score: 0.87 })]} />);
    expect(screen.getByTestId('analogy-score-0')).toHaveTextContent('87%');
  });

  it('truncates headline to at most 80 characters', () => {
    const longHeadline = 'A'.repeat(100);
    render(<SidePanelAnalogies analogies={[buildAnalogy({ headline: longHeadline })]} />);
    const headlineEl = screen.getByTestId('analogy-headline-0');
    // Truncated headline is 79 chars + ellipsis = 80 rendered chars visible (≤80)
    expect(headlineEl.textContent!.length).toBeLessThanOrEqual(80);
  });

  it('renders only the first 3 when more than 3 analogies provided', () => {
    const analogies = Array.from({ length: 5 }, (_, i) =>
      buildAnalogy({ event_id: String(i), similarity_score: 0.9 - i * 0.1 }),
    );
    render(<SidePanelAnalogies analogies={analogies} />);
    expect(screen.getAllByTestId(/^analogy-item-/)).toHaveLength(3);
  });
});
