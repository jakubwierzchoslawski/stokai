/**
 * supercluster.worker.ts — Web Worker: builds Supercluster index off the main thread.
 *
 * Import in the host via Vite's worker URL pattern:
 *   new Worker(new URL('./workers/supercluster.worker.ts', import.meta.url), { type: 'module' })
 *
 * Message protocol:
 *   In:  WorkerRequest  { events, zoom, bbox }
 *   Out: WorkerResponse { clusters: FeatureCollection, individualEvents: EventPulse[] }
 *
 * PLAN-F-019 TASK-004
 */

import type { WorkerRequest, WorkerResponse, EventPulse } from '../types/map.types';
import { buildEventProperties } from '../lib/cluster-properties';

// Supercluster is a CommonJS module; import the default export.
// When bundled by Vite the named import resolves correctly.
// eslint-disable-next-line @typescript-eslint/no-require-imports, @typescript-eslint/no-explicit-any
const Supercluster = (require('supercluster') as any).default ?? require('supercluster');

const MIN_ZOOM = 0;
const MAX_ZOOM = 7;
const CLUSTER_RADIUS = 60;

// ── Message handler ───────────────────────────────────────────────────────────

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const { events, zoom, bbox } = event.data;

  // Partition: intensity-5 events and zoom≥7 events always bypass clustering.
  const individualEvents: EventPulse[] = [];
  const clusterableEvents: EventPulse[] = [];

  for (const e of events) {
    if (e.intensity === 5 || zoom >= MAX_ZOOM) {
      individualEvents.push(e);
    } else {
      clusterableEvents.push(e);
    }
  }

  // Build GeoJSON point features for Supercluster.
  const points: GeoJSON.Feature<GeoJSON.Point>[] = clusterableEvents.map(
    (e) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [e.lon, e.lat] },
      properties: buildEventProperties(e),
    }),
  );

  // Construct and load the Supercluster index.
  const index = new Supercluster({
    minZoom: MIN_ZOOM,
    maxZoom: MAX_ZOOM - 1,
    radius: CLUSTER_RADIUS,
    // clusterProperties is passed here but relies on Supercluster's expression
    // language. For the numeric-expansion approach, the accumulation happens
    // automatically because each point property already carries count_CATEGORY.
  });

  index.load(points);

  // Retrieve clusters for the current viewport.
  const clusters = index.getClusters(bbox, Math.floor(zoom));

  const response: WorkerResponse = {
    clusters: {
      type: 'FeatureCollection',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      features: clusters as unknown as any[],
    },
    individualEvents,
  };

  self.postMessage(response);
};

// Required for TypeScript to treat this as a module.
export {};
