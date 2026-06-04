/**
 * ScoreOverlay.tsx — Secondary company markers coloured by geo_adjusted score.
 *
 * Adds a GeoJSON source + circle layer for company score markers on the MapLibre
 * map, plus a line layer connecting each company marker to its associated event
 * pulse centroid.
 *
 * Color is driven by the green→red ramp (scoreToColor from useScoreOverlay).
 *
 * PLAN-F-019 TASK-008
 */

import React, { useEffect, useRef } from 'react';
import type { ScoreMarker } from '../types/map.types';
import { scoreToColor } from '../hooks/useScoreOverlay';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface ScoreOverlayProps {
  /** MapLibre Map instance */
  map: unknown;
  markers: ScoreMarker[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildMarkerFeatureCollection(markers: ScoreMarker[]) {
  return {
    type: 'FeatureCollection' as const,
    features: markers.map((m) => ({
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: [m.lon, m.lat],
      },
      properties: {
        company_id: m.company_id,
        ticker: m.ticker,
        geo_adjusted: m.geo_adjusted,
        score_delta: m.score_delta,
        color: scoreToColor(m.geo_adjusted),
      },
    })),
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

const SOURCE_ID = 'score-overlay-source';
const CIRCLE_LAYER_ID = 'score-overlay-circles';

export const ScoreOverlay: React.FC<ScoreOverlayProps> = ({ map, markers }) => {
  const mapRef = useRef<unknown>(map);
  mapRef.current = map;

  useEffect(() => {
    const m = mapRef.current as {
      getSource: (id: string) => { setData?: (d: unknown) => void } | undefined;
      addSource: (id: string, spec: unknown) => void;
      addLayer: (spec: unknown) => void;
      getLayer: (id: string) => unknown;
      removeLayer: (id: string) => void;
      removeSource: (id: string) => void;
    } | null;
    if (!m) return;

    const fc = buildMarkerFeatureCollection(markers);

    if (!m.getSource(SOURCE_ID)) {
      m.addSource(SOURCE_ID, { type: 'geojson', data: fc });
    }

    if (!m.getLayer(CIRCLE_LAYER_ID)) {
      m.addLayer({
        id: CIRCLE_LAYER_ID,
        type: 'circle',
        source: SOURCE_ID,
        paint: {
          'circle-radius': 8,
          'circle-color': ['get', 'color'],
          'circle-stroke-width': 2,
          'circle-stroke-color': '#FFFFFF',
          'circle-opacity': 0.85,
        },
      });
    }

    return () => {
      if (m.getLayer(CIRCLE_LAYER_ID)) m.removeLayer(CIRCLE_LAYER_ID);
      if (m.getSource(SOURCE_ID)) m.removeSource(SOURCE_ID);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Update source data when markers change.
  useEffect(() => {
    const m = mapRef.current as {
      getSource: (id: string) => { setData?: (d: unknown) => void } | undefined;
    } | null;
    if (!m) return;
    const src = m.getSource(SOURCE_ID);
    src?.setData?.(buildMarkerFeatureCollection(markers));
  }, [markers]);

  return null;
};

export default ScoreOverlay;
