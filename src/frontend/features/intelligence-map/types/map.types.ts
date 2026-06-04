/**
 * map.types.ts — Core TypeScript interfaces for the Intelligence Map feature.
 *
 * PLAN-F-019 TASK-001
 */

// GeoJSON is expected to be provided by maplibre-gl's bundled types.
// We declare the namespace minimally here so this file has no runtime deps.
declare namespace GeoJSON {
  interface FeatureCollection {
    type: 'FeatureCollection';
    features: Feature[];
  }
  interface Feature {
    type: 'Feature';
    geometry: Geometry;
    properties: Record<string, unknown> | null;
  }
  interface Geometry {
    type: string;
    coordinates: unknown;
  }
}

// ── Core event model ───────────────────────────────────────────────────────────

export interface EventPulse {
  /** UUID */
  event_id: string;
  category: string[];
  intensity: 1 | 2 | 3 | 4 | 5;
  headline: string;
  /** ISO 8601 */
  timestamp: string;
  lat: number;
  lon: number;
  /** ISO 8601 */
  relevance_window_end: string;
  affected_companies: Array<{
    company_id: string;
    ticker: string;
    score_delta: number;
  }>;
}

// ── Cluster aggregation properties ────────────────────────────────────────────

export interface ClusterProps {
  /** category → count within the cluster */
  categories: Record<string, number>;
  /** highest intensity among cluster members (1–5) */
  max_intensity: number;
  event_count: number;
}

// ── Score overlay model ────────────────────────────────────────────────────────

export interface ScoreMarker {
  company_id: string;
  ticker: string;
  lat: number;
  lon: number;
  /** 0–100; drives green → red color ramp */
  geo_adjusted: number;
  /** new_geo_adjusted - previous */
  score_delta: number;
}

// ── Web Worker message contracts ──────────────────────────────────────────────

export interface WorkerRequest {
  events: EventPulse[];
  zoom: number;
  /** [west, south, east, north] */
  bbox: [number, number, number, number];
}

export interface WorkerResponse {
  clusters: GeoJSON.FeatureCollection;
  /** intensity-5 events (all zoom levels) or all events at zoom ≥ 7 */
  individualEvents: EventPulse[];
}
