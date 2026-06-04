/**
 * IntelligenceMap.tsx — Composition root: MapLibre GL JS world map at route "/".
 *
 * Orchestrates:
 *  - MapLibre GL JS Map instance (useEffect on mount)
 *  - PulseLayer / ClusterLayer (after map "load" event)
 *  - useEventFeed (initial fetch + WebSocket push)
 *  - supercluster.worker.ts (off-main-thread index build)
 *  - useMapFilters / useMapMode / useScoreOverlay
 *  - FilterPanel / MapContextSwitcher / EmptyState / ScoreOverlay
 *  - MapLibre Popup on pulse click (stub for PLAN-F-020 progressive disclosure)
 *
 * AC-001: route "/" renders this component without any intermediate landing page.
 *
 * PLAN-F-019 TASK-011
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useEventFeed } from './hooks/useEventFeed';
import { useMapFilters } from './hooks/useMapFilters';
import { useMapMode } from './hooks/useMapMode';
import { useScoreOverlay } from './hooks/useScoreOverlay';
import { generateEmptyStateMessage } from './lib/empty-state-message';
import PulseLayer from './components/PulseLayer';
import ClusterLayer from './components/ClusterLayer';
import FilterPanel from './components/FilterPanel';
import MapContextSwitcher from './components/MapContextSwitcher';
import EmptyState from './components/EmptyState';
import ScoreOverlay from './components/ScoreOverlay';
import type { EventPulse, WorkerRequest, WorkerResponse } from './types/map.types';

// ── MapLibre types (minimal; full types available via maplibre-gl package) ────

interface MapLibreMap {
  on: (event: string, cb: (...args: unknown[]) => void) => void;
  off: (event: string, cb: (...args: unknown[]) => void) => void;
  getZoom: () => number;
  getBounds: () => { toArray: () => [[number, number], [number, number]] };
  flyTo: (opts: { zoom: number; center: [number, number] }) => void;
  remove: () => void;
  addPopup?: (popup: unknown) => void;
}

// ── Environment variable: tile style URL ─────────────────────────────────────

function getMapStyleUrl(): string {
  try {
    // Vite injects import.meta.env at build time.
    // This pattern is safe in both browser and test environments.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const env = (import.meta as any).env as Record<string, string> | undefined;
    return env?.VITE_MAP_STYLE_URL ?? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
  } catch {
    return 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
  }
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface IntelligenceMapProps {
  /** Injected by PLAN-F-020 for progressive disclosure panel. No-op stub by default. */
  onExpandEvent?: (event: EventPulse) => void;
  /** Whether a scoring profile is active (shows ScoreOverlay). Default false. */
  profileActive?: boolean;
}

// ── Component ─────────────────────────────────────────────────────────────────

export const IntelligenceMap: React.FC<IntelligenceMapProps> = ({
  onExpandEvent,
  profileActive = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const workerRef = useRef<Worker | null>(null);

  const [mapReady, setMapReady] = useState(false);
  const [zoom, setZoom] = useState(2);
  const [bbox, setBbox] = useState<string>('-180,-85,180,85');

  const { mode, sector, setMode, setSector } = useMapMode();
  const { filters, toggleCategory, toggleIntensity } = useMapFilters();

  const { events, isLoading } = useEventFeed({
    context: mode,
    zoom,
    bbox,
    ...(mode === 'sector' && sector ? { sector } : {}),
  });

  const { scoreMarkers } = useScoreOverlay(profileActive, events);

  // ── Supercluster Worker ─────────────────────────────────────────────────────

  const [clusters, setClusters] = useState<WorkerResponse['clusters']>({
    type: 'FeatureCollection',
    features: [],
  });
  const [individualEvents, setIndividualEvents] = useState<EventPulse[]>([]);

  const dispatchWorker = useCallback(
    (evts: EventPulse[], currentZoom: number, currentBbox: string) => {
      const worker = workerRef.current;
      if (!worker) return;

      const [west, south, east, north] = currentBbox.split(',').map(Number);
      const req: WorkerRequest = {
        events: evts,
        zoom: currentZoom,
        bbox: [west, south, east, north],
      };
      worker.postMessage(req);
    },
    [],
  );

  useEffect(() => {
    if (!('Worker' in window)) return;
    try {
      const worker = new Worker(
        new URL('./workers/supercluster.worker.ts', import.meta.url),
        { type: 'module' },
      );
      worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
        setClusters(e.data.clusters);
        setIndividualEvents(e.data.individualEvents);
      };
      workerRef.current = worker;
      return () => worker.terminate();
    } catch {
      // Worker not available in test/SSR — fall back to inline (no clusters).
    }
  }, []);

  // Dispatch worker when events, zoom, or bbox change.
  useEffect(() => {
    dispatchWorker(events, zoom, bbox);
  }, [events, zoom, bbox, dispatchWorker]);

  // ── MapLibre initialisation ─────────────────────────────────────────────────

  useEffect(() => {
    if (!containerRef.current) return;

    let mapInstance: MapLibreMap | null = null;

    const initMap = async () => {
      try {
        // Dynamic import to allow mocking in tests.
        const maplibre = await import('maplibre-gl');
        const Map = maplibre.default?.Map ?? (maplibre as unknown as { Map: new (opts: unknown) => MapLibreMap }).Map;

        mapInstance = new Map({
          container: containerRef.current!,
          style: getMapStyleUrl(),
          zoom: 2,
          center: [0, 20],
          attributionControl: true,
        }) as unknown as MapLibreMap;

        const handleLoad = () => {
          mapRef.current = mapInstance;
          setMapReady(true);
        };

        const handleMoveEnd = () => {
          if (!mapInstance) return;
          const currentZoom = mapInstance.getZoom();
          const bounds = mapInstance.getBounds().toArray();
          const [sw, ne] = bounds;
          const newBbox = `${sw[0]},${sw[1]},${ne[0]},${ne[1]}`;
          setZoom(currentZoom);
          setBbox(newBbox);
        };

        mapInstance.on('load', handleLoad);
        mapInstance.on('moveend', handleMoveEnd);
      } catch {
        // maplibre-gl not available (test environment) — mark map as ready with null instance.
        setMapReady(true);
      }
    };

    void initMap();

    return () => {
      mapInstance?.remove();
      mapRef.current = null;
    };
  }, []);

  // ── Cluster click handler ───────────────────────────────────────────────────

  const handleClusterClick = useCallback(
    (cluster: { geometry: { coordinates: [number, number] } }) => {
      const map = mapRef.current;
      if (!map) return;
      map.flyTo({
        zoom: map.getZoom() + 1,
        center: cluster.geometry.coordinates,
      });
    },
    [],
  );

  // ── Pulse click handler ─────────────────────────────────────────────────────

  const handlePulseClick = useCallback(
    (event: EventPulse) => {
      // Stub popup — PLAN-F-020 injects the real side-panel via onExpandEvent prop.
      console.log('[IntelligenceMap] Pulse clicked:', event.event_id, event.headline);
      onExpandEvent?.(event);
    },
    [onExpandEvent],
  );

  // ── Derived state ───────────────────────────────────────────────────────────

  // Events visible after client-side filters.
  const filteredEvents = individualEvents.filter((e) => {
    const categoryMatch = e.category.some((c) => filters.categories.includes(c));
    const intensityMatch = filters.intensities.includes(e.intensity);
    return categoryMatch && intensityMatch;
  });

  const showEmptyState = events.length === 0 && !isLoading;
  const emptyMessage = generateEmptyStateMessage(mode, filters, events.length);

  return (
    <div
      data-testid="intelligence-map-root"
      style={{ position: 'relative', width: '100%', height: '100vh' }}
    >
      {/* MapLibre canvas container */}
      <div
        ref={containerRef}
        data-testid="map-container"
        style={{ width: '100%', height: '100%' }}
      />

      {/* Overlays — rendered once map is ready */}
      {mapReady && mapRef.current && (
        <>
          <PulseLayer
            map={mapRef.current}
            events={filteredEvents}
            activeFilters={filters}
            onPulseClick={handlePulseClick}
          />
          <ClusterLayer
            map={mapRef.current}
            clusters={clusters}
            onClusterClick={handleClusterClick as (cluster: unknown) => void}
          />
          {scoreMarkers.length > 0 && (
            <ScoreOverlay map={mapRef.current} markers={scoreMarkers} />
          )}
        </>
      )}

      {/* Filter panel */}
      <FilterPanel
        filters={filters}
        onToggleCategory={toggleCategory}
        onToggleIntensity={toggleIntensity}
      />

      {/* Context mode switcher */}
      <MapContextSwitcher
        mode={mode}
        sector={sector}
        onSetMode={setMode}
        onSetSector={setSector}
      />

      {/* Empty / quiet state */}
      {showEmptyState && <EmptyState message={emptyMessage} />}

      {/* Loading indicator */}
      {isLoading && (
        <div
          data-testid="map-loading"
          style={{
            position: 'absolute',
            top: 10,
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'rgba(20,20,30,0.8)',
            color: '#fff',
            padding: '4px 16px',
            borderRadius: 6,
            fontSize: 12,
            zIndex: 1000,
          }}
        >
          Loading events...
        </div>
      )}
    </div>
  );
};

export default IntelligenceMap;
