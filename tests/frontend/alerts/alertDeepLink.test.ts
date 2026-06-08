import { describe, it, expect } from 'vitest';
/**
 * Tests for alertDeepLink utility and MapPage deep-link behaviour.
 *
 * PLAN-F-025 TASK-009 + TASK-012
 */
import { buildEventLink } from '../../../src/frontend/lib/alertDeepLink';

describe('buildEventLink', () => {
  it('returns correct URL for given event_id, lat, lon', () => {
    const url = buildEventLink('abc-123', 38.9, -77);
    expect(url).toBe('/map?event=abc-123&lat=38.9&lon=-77');
  });

  it('produces URL parseable by URLSearchParams with correct keys', () => {
    const url = buildEventLink('evt-999', 51.5, -0.1);
    const full = `http://localhost${url}`;
    const params = new URLSearchParams(new URL(full).search);
    expect(params.get('event')).toBe('evt-999');
    expect(params.get('lat')).toBe('51.5');
    expect(params.get('lon')).toBe('-0.1');
  });

  it('handles zero lat/lon', () => {
    const url = buildEventLink('zero-event', 0, 0);
    expect(url).toContain('lat=0');
    expect(url).toContain('lon=0');
  });
});
