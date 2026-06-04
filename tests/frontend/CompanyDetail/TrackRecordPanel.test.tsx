/**
 * Tests for TrackRecordPanel component.
 *
 * Tests:
 * - Accuracy line hidden when directionalAccuracyT1d is null
 * - Accuracy line shown when directionalAccuracyT1d is not null
 * - Renders track record rows
 * - Shows empty state when no track record
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { TrackRecordPanel } from '../../../src/frontend/pages/CompanyDetail/TrackRecordPanel';
import type { TrackRecordItem } from '../../../src/frontend/pages/CompanyDetail/types';

function makeTrackItem(id: string, overrides: Partial<TrackRecordItem> = {}): TrackRecordItem {
  return {
    rec_id: id,
    generated_at: '2024-01-01T00:00:00Z',
    action_signal: 'BUY_OPP',
    direction: 'bullish',
    confidence: 0.8,
    actual_t1d: 0.02,
    actual_t1w: null,
    correct_t1d: true,
    correct_t1w: null,
    ...overrides,
  };
}

describe('TrackRecordPanel', () => {
  it('hides accuracy line when directionalAccuracyT1d is null', () => {
    render(
      <TrackRecordPanel
        trackRecord={[makeTrackItem('r1')]}
        directionalAccuracyT1d={null}
      />,
    );
    expect(screen.queryByTestId('accuracy-line')).not.toBeInTheDocument();
  });

  it('shows accuracy line when directionalAccuracyT1d is provided', () => {
    render(
      <TrackRecordPanel
        trackRecord={[makeTrackItem('r1')]}
        directionalAccuracyT1d={0.667}
      />,
    );
    const accuracyLine = screen.getByTestId('accuracy-line');
    expect(accuracyLine).toBeInTheDocument();
    expect(accuracyLine.textContent).toContain('66.7%');
  });

  it('renders track record rows', () => {
    const items = [makeTrackItem('r1'), makeTrackItem('r2')];
    render(<TrackRecordPanel trackRecord={items} directionalAccuracyT1d={null} />);

    const table = screen.getByTestId('track-record-table');
    expect(table).toBeInTheDocument();
    expect(screen.getByTestId('track-record-row-r1')).toBeInTheDocument();
    expect(screen.getByTestId('track-record-row-r2')).toBeInTheDocument();
  });

  it('shows empty state when no track record', () => {
    render(<TrackRecordPanel trackRecord={[]} directionalAccuracyT1d={null} />);
    expect(screen.getByTestId('track-record-empty')).toBeInTheDocument();
  });

  it('renders "—" for null actual_t1d', () => {
    const items = [makeTrackItem('r1', { actual_t1d: null, correct_t1d: null })];
    render(<TrackRecordPanel trackRecord={items} directionalAccuracyT1d={null} />);
    // The t1d cell should show "—"
    expect(screen.getByTestId('correct-t1d-r1').textContent).toBe('—');
  });

  it('shows correct/incorrect indicators', () => {
    const items = [
      makeTrackItem('r-correct', { correct_t1d: true }),
      makeTrackItem('r-wrong', { correct_t1d: false }),
    ];
    render(<TrackRecordPanel trackRecord={items} directionalAccuracyT1d={null} />);

    expect(screen.getByTestId('correct-t1d-r-correct').textContent).toBe('✓');
    expect(screen.getByTestId('correct-t1d-r-wrong').textContent).toBe('✗');
  });
});
