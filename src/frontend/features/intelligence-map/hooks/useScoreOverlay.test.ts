/**
 * useScoreOverlay.test.ts — TDD tests for the useScoreOverlay hook.
 *
 * PLAN-F-019 TASK-008
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useScoreOverlay, scoreToColor } from './useScoreOverlay';

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

// ── useScoreOverlay — profileActive=false ────────────────────────────────────

describe('useScoreOverlay(false)', () => {
  it('returns empty scoreMarkers', () => {
    const wsClose = jest.fn();
    global.WebSocket = jest.fn().mockImplementation(() => ({
      addEventListener: jest.fn(),
      close: wsClose,
    })) as unknown as typeof WebSocket;

    const { result } = renderHook(() => useScoreOverlay(false));
    expect(result.current.scoreMarkers).toHaveLength(0);
  });

  it('does not establish a WebSocket connection', () => {
    const wsCtor = jest.fn();
    global.WebSocket = wsCtor as unknown as typeof WebSocket;

    renderHook(() => useScoreOverlay(false));
    expect(wsCtor).not.toHaveBeenCalled();
  });
});

// ── useScoreOverlay — profileActive=true ─────────────────────────────────────

describe('useScoreOverlay(true)', () => {
  let capturedMessageListener: ((e: MessageEvent) => void) | null = null;
  const wsClose = jest.fn();

  beforeEach(() => {
    capturedMessageListener = null;
    wsClose.mockClear();
    global.WebSocket = jest.fn().mockImplementation(() => ({
      addEventListener: jest.fn((event: string, cb: (e: MessageEvent) => void) => {
        if (event === 'message') capturedMessageListener = cb;
      }),
      close: wsClose,
    })) as unknown as typeof WebSocket;
  });

  it('receiving a GeoModifierPayload with 2 companies → scoreMarkers has 2 entries', async () => {
    const { result } = renderHook(() => useScoreOverlay(true));

    act(() => {
      capturedMessageListener?.({
        data: JSON.stringify({
          affected_companies: {
            'company-1': 75,
            'company-2': 30,
          },
        }),
      } as MessageEvent);
    });

    await waitFor(() => {
      expect(result.current.scoreMarkers).toHaveLength(2);
    });
  });

  it('second payload for the same company updates (not duplicates) the entry', async () => {
    const { result } = renderHook(() => useScoreOverlay(true));

    act(() => {
      capturedMessageListener?.({
        data: JSON.stringify({ affected_companies: { 'company-1': 50 } }),
      } as MessageEvent);
    });
    await waitFor(() => expect(result.current.scoreMarkers).toHaveLength(1));

    act(() => {
      capturedMessageListener?.({
        data: JSON.stringify({ affected_companies: { 'company-1': 80 } }),
      } as MessageEvent);
    });
    await waitFor(() => {
      expect(result.current.scoreMarkers).toHaveLength(1);
      expect(result.current.scoreMarkers[0].geo_adjusted).toBe(80);
    });
  });

  it('unmounting calls ws.close() exactly once', () => {
    const { unmount } = renderHook(() => useScoreOverlay(true));
    unmount();
    expect(wsClose).toHaveBeenCalledTimes(1);
  });
});
