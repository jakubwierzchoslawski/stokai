import { describe, it, expect, vi, beforeEach } from 'vitest';
/**
 * useScoreOverlay.test.ts â€” TDD tests for the useScoreOverlay hook.
 *
 * PLAN-F-019 TASK-008
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useScoreOverlay, scoreToColor } from './useScoreOverlay';

// â”€â”€ scoreToColor unit tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('scoreToColor', () => {
  it('geo_adjusted=20 â†’ red range (hsl(0, ...))', () => {
    expect(scoreToColor(20)).toMatch(/hsl\(0,/);
  });

  it('geo_adjusted=50 â†’ amber range (hsl(40, ...))', () => {
    expect(scoreToColor(50)).toMatch(/hsl\(40,/);
  });

  it('geo_adjusted=80 â†’ green range (hsl(120, ...))', () => {
    expect(scoreToColor(80)).toMatch(/hsl\(120,/);
  });

  it('boundary 33 â†’ red', () => {
    expect(scoreToColor(33)).toMatch(/hsl\(0,/);
  });

  it('boundary 34 â†’ amber', () => {
    expect(scoreToColor(34)).toMatch(/hsl\(40,/);
  });

  it('boundary 67 â†’ green', () => {
    expect(scoreToColor(67)).toMatch(/hsl\(120,/);
  });
});

// â”€â”€ useScoreOverlay â€” profileActive=false â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('useScoreOverlay(false)', () => {
  it('returns empty scoreMarkers', () => {
    const wsClose = vi.fn();
    global.WebSocket = vi.fn().mockImplementation(() => ({
      addEventListener: vi.fn(),
      close: wsClose,
    })) as unknown as typeof WebSocket;

    const { result } = renderHook(() => useScoreOverlay(false));
    expect(result.current.scoreMarkers).toHaveLength(0);
  });

  it('does not establish a WebSocket connection', () => {
    const wsCtor = vi.fn();
    global.WebSocket = wsCtor as unknown as typeof WebSocket;

    renderHook(() => useScoreOverlay(false));
    expect(wsCtor).not.toHaveBeenCalled();
  });
});

// â”€â”€ useScoreOverlay â€” profileActive=true â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('useScoreOverlay(true)', () => {
  let capturedMessageListener: ((e: MessageEvent) => void) | null = null;
  const wsClose = vi.fn();

  beforeEach(() => {
    capturedMessageListener = null;
    wsClose.mockClear();
    global.WebSocket = vi.fn().mockImplementation(() => ({
      addEventListener: vi.fn((event: string, cb: (e: MessageEvent) => void) => {
        if (event === 'message') capturedMessageListener = cb;
      }),
      close: wsClose,
    })) as unknown as typeof WebSocket;
  });

  it('receiving a GeoModifierPayload with 2 companies â†’ scoreMarkers has 2 entries', async () => {
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
