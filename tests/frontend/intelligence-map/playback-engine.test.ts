/**
 * playback-engine.test.ts — TDD tests for PlaybackEngine.
 *
 * PLAN-F-021 TASK-003
 */

import { PlaybackEngine } from '../../../src/frontend/features/intelligence-map/lib/playback-engine';
import type { EventPulse } from '../../../src/frontend/features/intelligence-map/types/map.types';

function makeEvent(id: string, timestamp: string): EventPulse {
  return {
    event_id: id,
    category: ['geopolitical'],
    intensity: 3,
    headline: `Event ${id}`,
    timestamp,
    lat: 0,
    lon: 0,
    relevance_window_end: timestamp,
    affected_companies: [],
  };
}

const BASE_MS = new Date('2025-01-01T00:00:00.000Z').getTime();
const EVENT_T0 = makeEvent('e1', new Date(BASE_MS).toISOString());
const EVENT_T30 = makeEvent('e2', new Date(BASE_MS + 1_800_000).toISOString());
const EVENT_T60 = makeEvent('e3', new Date(BASE_MS + 3_600_000).toISOString());

describe('PlaybackEngine', () => {
  it('tick(0) at 1x → 1 event visible (T+0 only)', () => {
    const engine = new PlaybackEngine([EVENT_T0, EVENT_T30, EVENT_T60], '1x');
    const { visibleEvents } = engine.tick(0);
    expect(visibleEvents).toHaveLength(1);
    expect(visibleEvents[0].event_id).toBe('e1');
  });

  it('tick(1_800_000) at 1x → 2 events visible (T+0 and T+30)', () => {
    const engine = new PlaybackEngine([EVENT_T0, EVENT_T30, EVENT_T60], '1x');
    const { visibleEvents } = engine.tick(1_800_000);
    expect(visibleEvents).toHaveLength(2);
    const ids = visibleEvents.map((e) => e.event_id).sort();
    expect(ids).toEqual(['e1', 'e2']);
  });

  it('tick(3_600_000) at 1x → all 3 events; virtualNow equals virtualWindowEnd', () => {
    const engine = new PlaybackEngine([EVENT_T0, EVENT_T30, EVENT_T60], '1x');
    const { visibleEvents, virtualNow } = engine.tick(3_600_000);
    expect(visibleEvents).toHaveLength(3);
    expect(virtualNow.getTime()).toBe(new Date(EVENT_T60.timestamp).getTime());
  });

  it('16× speed: tick(225_000) → all 3 events visible — AC-003', () => {
    const engine = new PlaybackEngine([EVENT_T0, EVENT_T30, EVENT_T60], '16x');
    const { visibleEvents } = engine.tick(225_000);
    expect(visibleEvents).toHaveLength(3);
  });

  it('4× speed: tick(900_000) → all 3 events visible', () => {
    const engine = new PlaybackEngine([EVENT_T0, EVENT_T30, EVENT_T60], '4x');
    const { visibleEvents } = engine.tick(900_000);
    expect(visibleEvents).toHaveLength(3);
  });

  it('reset() after tick(3_600_000) → next tick(0) returns 1 event', () => {
    const engine = new PlaybackEngine([EVENT_T0, EVENT_T30, EVENT_T60], '1x');
    engine.tick(3_600_000);
    engine.reset();
    const { visibleEvents } = engine.tick(0);
    expect(visibleEvents).toHaveLength(1);
    expect(visibleEvents[0].event_id).toBe('e1');
  });

  it('empty events array → tick(any) returns { visibleEvents: [], virtualNow: epoch }', () => {
    const engine = new PlaybackEngine([], '1x');
    const { visibleEvents, virtualNow } = engine.tick(5_000_000);
    expect(visibleEvents).toHaveLength(0);
    expect(virtualNow.getTime()).toBe(0);
  });

  it('events with identical timestamps all appear in the same tick', () => {
    const SAME_TS = new Date(BASE_MS + 1_000_000).toISOString();
    const evA = makeEvent('a', SAME_TS);
    const evB = makeEvent('b', SAME_TS);
    const evC = makeEvent('c', SAME_TS);
    const engine = new PlaybackEngine([evA, evB, evC], '1x');
    const { visibleEvents } = engine.tick(1_000_000);
    expect(visibleEvents).toHaveLength(3);
  });

  it('virtualNow is clamped to virtualWindowEnd with large elapsed', () => {
    const engine = new PlaybackEngine([EVENT_T0, EVENT_T60], '1x');
    const { virtualNow } = engine.tick(999_999_999);
    expect(virtualNow.getTime()).toBe(new Date(EVENT_T60.timestamp).getTime());
  });
});
