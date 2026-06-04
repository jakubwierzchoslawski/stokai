/**
 * time-mode-empty-state.test.ts — Tests for generateTimeModeEmptyStateMessage.
 *
 * PLAN-F-021 TASK-009
 */

import { generateTimeModeEmptyStateMessage } from '../../../src/frontend/features/intelligence-map/lib/time-mode-empty-state';

const DATE_RANGE = { from_date: '2025-01-01', to_date: '2025-01-31' };

describe('generateTimeModeEmptyStateMessage', () => {
  it('historical, eventCount=0, dateRange set → contains date range text', () => {
    const msg = generateTimeModeEmptyStateMessage('historical', DATE_RANGE, 0);
    expect(msg).toContain('2025-01-01');
    expect(msg).toContain('2025-01-31');
    expect(msg.toLowerCase()).toContain('widen');
  });

  it('historical, eventCount=0, no dateRange → asks to select date range', () => {
    const msg = generateTimeModeEmptyStateMessage('historical', null, 0);
    expect(msg.toLowerCase()).toContain('date range');
    expect(msg.toLowerCase()).toContain('select');
  });

  it('playback, isComplete=false, eventCount=0 → no events message', () => {
    const msg = generateTimeModeEmptyStateMessage('playback', DATE_RANGE, 0, false);
    expect(msg.toLowerCase()).toContain('no events');
    expect(msg.toLowerCase()).toContain('date range');
  });

  it('playback, isComplete=true → "Playback complete" message with event count', () => {
    const msg = generateTimeModeEmptyStateMessage('playback', DATE_RANGE, 5, true);
    expect(msg.toLowerCase()).toContain('playback complete');
    expect(msg).toContain('5');
  });

  it('live → delegates to live fallback message (no dates)', () => {
    const msg = generateTimeModeEmptyStateMessage('live', null, 0);
    expect(msg.length).toBeGreaterThan(0);
    expect(msg).not.toContain('2025');
  });

  it('fallback: historical with events > 0 → returns non-empty message', () => {
    const msg = generateTimeModeEmptyStateMessage('historical', DATE_RANGE, 5);
    expect(msg.length).toBeGreaterThan(0);
  });
});
