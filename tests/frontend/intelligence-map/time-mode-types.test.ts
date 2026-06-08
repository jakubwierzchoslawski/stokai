import { describe, it, expect } from 'vitest';
/**
 * time-mode-types.test.ts â€” Tests for time-mode type definitions (TASK-001).
 *
 * PLAN-F-021 TASK-001
 */

// Type-level tests â€” just confirm the barrel export works.
import type {
  TimeMode,
  PlaybackSpeed,
  DateRange,
  ScoreAtTime,
  TimeModeContext,
} from '../../../src/frontend/features/intelligence-map/types/time-mode.types';

describe('time-mode type definitions', () => {
  it('TimeMode type covers live | historical | playback', () => {
    const live: TimeMode = 'live';
    const historical: TimeMode = 'historical';
    const playback: TimeMode = 'playback';
    expect([live, historical, playback]).toHaveLength(3);
  });

  it('PlaybackSpeed covers 1x | 4x | 16x', () => {
    const s1: PlaybackSpeed = '1x';
    const s4: PlaybackSpeed = '4x';
    const s16: PlaybackSpeed = '16x';
    expect([s1, s4, s16]).toHaveLength(3);
  });

  it('DateRange has from_date and to_date as strings', () => {
    const range: DateRange = { from_date: '2025-01-01', to_date: '2025-01-31' };
    expect(typeof range.from_date).toBe('string');
    expect(typeof range.to_date).toBe('string');
  });

  it('ScoreAtTime has required fields', () => {
    const score: ScoreAtTime = {
      company_id: 'abc',
      indicator_id: 'ind',
      score: 75,
      geo_adjusted: 70,
      computed_at: '2025-01-01T00:00:00Z',
    };
    expect(score.company_id).toBe('abc');
    expect(score.score).toBe(75);
  });

  it('TimeModeContext has timeMode, dateRange, playbackSpeed, currentTick', () => {
    const ctx: TimeModeContext = {
      timeMode: 'live',
      dateRange: null,
      playbackSpeed: '1x',
      currentTick: null,
    };
    expect(ctx.timeMode).toBe('live');
    expect(ctx.currentTick).toBeNull();
  });
});
