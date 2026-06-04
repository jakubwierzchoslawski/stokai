/**
 * useScoreOverlay.ts — Subscribes to ws/scores; maintains company score delta map.
 *
 * When profileActive=false: returns empty ScoreMarker[]; no WebSocket subscription.
 * When profileActive=true: subscribes to ws/scores channel and updates a company
 * score map from GeoModifierPayload messages.
 *
 * GeoModifierPayload shape (from PLAN-F-018):
 *   { affected_companies: { [company_id]: new_geo_adjusted }, ... }
 *
 * Company lat/lon is resolved from the current event list (in-memory join on
 * affected_companies[].company_id — no extra fetch required).
 *
 * PLAN-F-019 TASK-008
 */

import { useEffect, useRef, useState } from 'react';
import type { ScoreMarker, EventPulse } from '../types/map.types';

// ── WebSocket subscription ────────────────────────────────────────────────────

export interface WsScoreSubscription {
  unsubscribe: () => void;
}

export type OnScoreUpdateCallback = (payload: GeoModifierPayload) => void;

/** Shape of the GeoModifierPayload broadcast by PLAN-F-018 */
export interface GeoModifierPayload {
  affected_companies: Record<string, number>; // company_id → new_geo_adjusted
  [key: string]: unknown;
}

export function subscribeToScoreChannel(
  onUpdate: OnScoreUpdateCallback,
): WsScoreSubscription {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/scores`;

  let socket: WebSocket | null = null;
  let closed = false;

  function connect() {
    if (closed) return;
    socket = new WebSocket(wsUrl);

    socket.addEventListener('message', (msg) => {
      try {
        const parsed: unknown = JSON.parse(msg.data as string);
        if (
          parsed !== null &&
          typeof parsed === 'object' &&
          'affected_companies' in (parsed as Record<string, unknown>)
        ) {
          onUpdate(parsed as GeoModifierPayload);
        }
      } catch {
        // Malformed messages silently dropped.
      }
    });

    socket.addEventListener('error', () => {
      // Errors swallowed; reconnection is a future concern.
    });
  }

  connect();

  return {
    unsubscribe() {
      closed = true;
      socket?.close();
      socket = null;
    },
  };
}

// ── Color ramp ────────────────────────────────────────────────────────────────

/**
 * Map a geo_adjusted score (0–100) to an HSL color string.
 * 0–33:  red   (low score)
 * 34–66: amber (medium)
 * 67–100: green (high score)
 */
export function scoreToColor(geoAdjusted: number): string {
  if (geoAdjusted <= 33) return 'hsl(0, 80%, 50%)';
  if (geoAdjusted <= 66) return 'hsl(40, 80%, 50%)';
  return 'hsl(120, 60%, 40%)';
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseScoreOverlayResult {
  scoreMarkers: ScoreMarker[];
}

export function useScoreOverlay(
  profileActive: boolean,
  events: EventPulse[] = [],
): UseScoreOverlayResult {
  const [markerMap, setMarkerMap] = useState<Map<string, ScoreMarker>>(new Map());
  const subscriptionRef = useRef<WsScoreSubscription | null>(null);
  const eventsRef = useRef<EventPulse[]>(events);
  eventsRef.current = events;

  useEffect(() => {
    if (!profileActive) {
      // Clean up if profile was previously active.
      subscriptionRef.current?.unsubscribe();
      subscriptionRef.current = null;
      setMarkerMap(new Map());
      return;
    }

    const sub = subscribeToScoreChannel((payload: GeoModifierPayload) => {
      setMarkerMap((prev) => {
        const next = new Map(prev);
        for (const [companyId, newGeoAdjusted] of Object.entries(
          payload.affected_companies,
        )) {
          // Resolve lat/lon from the current events list (in-memory join).
          let lat = 0;
          let lon = 0;
          let ticker = companyId;
          outer: for (const ev of eventsRef.current) {
            for (const ac of ev.affected_companies) {
              if (ac.company_id === companyId) {
                lat = ev.lat;
                lon = ev.lon;
                ticker = ac.ticker;
                break outer;
              }
            }
          }

          const previous = prev.get(companyId);
          const previousScore = previous?.geo_adjusted ?? newGeoAdjusted;

          next.set(companyId, {
            company_id: companyId,
            ticker,
            lat,
            lon,
            geo_adjusted: newGeoAdjusted,
            score_delta: newGeoAdjusted - previousScore,
          });
        }
        return next;
      });
    });
    subscriptionRef.current = sub;

    return () => {
      sub.unsubscribe();
      subscriptionRef.current = null;
    };
  }, [profileActive]);

  const scoreMarkers: ScoreMarker[] = profileActive
    ? Array.from(markerMap.values())
    : [];

  return { scoreMarkers };
}
