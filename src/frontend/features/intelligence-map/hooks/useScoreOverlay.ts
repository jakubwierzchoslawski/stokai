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
import { apiSocket } from '@/lib/api/ws';
import type { ScoreMarker, EventPulse } from '../types/map.types';

/** Shape of the GeoModifierPayload broadcast by PLAN-F-018 */
export interface GeoModifierPayload {
  affected_companies: Record<string, number>; // company_id → new_geo_adjusted
  [key: string]: unknown;
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
  const eventsRef = useRef<EventPulse[]>(events);
  eventsRef.current = events;

  useEffect(() => {
    if (!profileActive) {
      setMarkerMap(new Map());
      return;
    }

    const handle = apiSocket('/ws/scores', {
      onMessage: (msg) => {
        const payload = msg as unknown as GeoModifierPayload;
        if (!payload || typeof payload.affected_companies !== 'object') return;
        setMarkerMap((prev) => {
          const next = new Map(prev);
          for (const [companyId, newGeoAdjusted] of Object.entries(
            payload.affected_companies,
          )) {
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
      },
      onClose: () => {
        // apiSocket handles auth; normal close on unmount.
      },
    });

    return () => handle.close();
  }, [profileActive]);

  const scoreMarkers: ScoreMarker[] = profileActive
    ? Array.from(markerMap.values())
    : [];

  return { scoreMarkers };
}
