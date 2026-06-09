import { describe, it, expect, vi, beforeEach } from 'vitest';
/**
 * useScoreOverlay.test.ts — TDD tests for the useScoreOverlay hook.
 *
 * PLAN-F-019 TASK-008
 * Updated for Phase 2a: mocks apiSocket instead of raw WebSocket.
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useScoreOverlay, scoreToColor } from './useScoreOverlay';

// ── Mock apiSocket ─────────────────────────────────────────────────────────────

vi.mock('@/lib/api/ws', () => {
  let lastOnMessage: ((m: unknown) => void) | null = null;
  let closeCount = 0;
  let socketCreated = false;
  return {
    apiSocket: (_path: string, handlers: { onMessage: (m: unknown) => void }) => {
      socketCreated = true;
      lastOnMessage = handlers.onMessage;
      return { close: () => { closeCount += 1; } };
    },
    __test__: {
      pushMessage: (m: unknown) => lastOnMessage?.(m),
      getCloseCount: () => closeCount,
      wasSocketCreated: () => socketCreated,
      reset: () => { lastOnMessage = null; closeCount = 0; socketCreated = false; },
    },
  };
});

import * as ws from '@/lib/api/ws';
const { __test__ } = ws as unknown as {
  __test__: {
    pushMessage: (m: unknown) => void;
    getCloseCount: () => number;
    wasSocketCreated: () => boolean;
    reset: () => void;
  };
};

// ── scoreToColor unit tests ───────────────────────────────────────────────────

describe('scoreToColor', () => {
  it('geo_adjusted=20 → red range (hsl(0, ...))', () => {
    expect(scoreToColor(20)).toMatch(/hsl\(0,/);
  });

  it('geo_adjusted=50 → amber range (hsl(40, ...))', () => {
    expect(scoreToColor(50)).toMatch(/hsl\(40,/);
  });

  it('geo_adjusted=80 → green range (hsl(120, ...))', () => {
    expect(scoreToColor(80)).toMatch(/hsl\(120,/);
  });

  it('boundary 33 → red', () => {
    expect(scoreToColor(33)).toMatch(/hsl\(0,/);
  });

  it('boundary 34 → amber', () => {
    expect(scoreToColor(34)).toMatch(/hsl\(40,/);
  });

  it('boundary 67 → green', () => {
    expect(scoreToColor(67)).toMatch(/hsl\(120,/);
  });
});

// ── useScoreOverlay — profileActive=false ─────────────────────────────────────

describe('useScoreOverlay(false)', () => {
  beforeEach(() => __test__.reset());

  it('returns empty scoreMarkers', () => {
    const { result } = renderHook(() => useScoreOverlay(false));
    expect(result.current.scoreMarkers).toHaveLength(0);
  });

  it('does not establish a WebSocket connection', () => {
    renderHook(() => useScoreOverlay(false));
    expect(__test__.wasSocketCreated()).toBe(false);
  });
});

// ── useScoreOverlay — profileActive=true ──────────────────────────────────────

describe('useScoreOverlay(true)', () => {
  beforeEach(() => __test__.reset());

  it('receiving a GeoModifierPayload with 2 companies → scoreMarkers has 2 entries', async () => {
    const { result } = renderHook(() => useScoreOverlay(true));

    act(() => {
      __test__.pushMessage({
        affected_companies: { 'company-1': 75, 'company-2': 30 },
      });
    });

    await waitFor(() => {
      expect(result.current.scoreMarkers).toHaveLength(2);
    });
  });

  it('second payload for the same company updates (not duplicates) the entry', async () => {
    const { result } = renderHook(() => useScoreOverlay(true));

    act(() => {
      __test__.pushMessage({ affected_companies: { 'company-1': 50 } });
    });
    await waitFor(() => expect(result.current.scoreMarkers).toHaveLength(1));

    act(() => {
      __test__.pushMessage({ affected_companies: { 'company-1': 80 } });
    });
    await waitFor(() => {
      expect(result.current.scoreMarkers).toHaveLength(1);
      expect(result.current.scoreMarkers[0].geo_adjusted).toBe(80);
    });
  });

  it('unmounting calls handle.close() exactly once', () => {
    const { unmount } = renderHook(() => useScoreOverlay(true));
    unmount();
    expect(__test__.getCloseCount()).toBe(1);
  });
});
