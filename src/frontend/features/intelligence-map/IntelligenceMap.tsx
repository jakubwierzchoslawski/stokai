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
 * Responsive layout (PLAN-N-014 TASK-005):
 *  - lg (≥1280px): map canvas + right side-panel in a flex row; panel w-[360px]
 *  - md (768–1279px): panel collapses to w-[280px], still visible
 *  - sm (<768px): panel hidden from flex row; rendered inside <Drawer side="right">
 *    with a fixed floating toggle button bottom-right to open it
 *
 * AC-001: route "/" renders this component without any intermediate landing page.
 *
 * PLAN-F-019 TASK-011
 * PLAN-N-014 TASK-005
 * PLAN-F-021 TASK-012 — time-mode wiring (Live / Historical / Playback)
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useNavigate } from 'react-router-dom';
import { env } from '@/lib/env';
import { useEventFeed } from './hooks/useEventFeed';
import { useMapFilters } from './hooks/useMapFilters';
import { useMapMode } from './hooks/useMapMode';
import { useScoreOverlay } from './hooks/useScoreOverlay';
import { useTimeModeState } from './hooks/useTimeModeState';
import { useHistoricalEvents } from './hooks/useHistoricalEvents';
import { usePlayback } from './hooks/usePlayback';
import { generateEmptyStateMessage } from './lib/empty-state-message';
import { generateTimeModeEmptyStateMessage } from './lib/time-mode-empty-state';
import PulseLayer from './components/PulseLayer';
import ClusterLayer from './components/ClusterLayer';
import { EventPopup } from './components/EventPopup';
import FilterPanel from './components/FilterPanel';
import MapContextSwitcher from './components/MapContextSwitcher';
import EmptyState from './components/EmptyState';
import ScoreOverlay from './components/ScoreOverlay';
import TimeModeToolbar from './components/TimeModeToolbar';
import PlaybackControls from './components/PlaybackControls';
import { Drawer } from '../shared/layout/Drawer';
import { useBreakpoint } from '../shared/hooks/useBreakpoint';
import type { EventPulse, WorkerRequest, WorkerResponse } from './types/map.types';
import type { DateRange } from './types/time-mode.types';

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
  const popupRef = useRef<{ remove: () => void } | null>(null);
  const popupRootRef = useRef<Root | null>(null);
  const navigate = useNavigate();

  const [mapReady, setMapReady] = useState(false);
  const [zoom, setZoom] = useState(2);
  const [bbox, setBbox] = useState<string>('-180,-85,180,85');
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Responsive breakpoint — drives panel layout strategy (PLAN-N-014 TASK-005)
  const breakpoint = useBreakpoint();
  const isMobile = breakpoint === 'sm'; // < 768px — panel goes into drawer

  const { mode, sector, setMode, setSector } = useMapMode();
  const { filters, toggleCategory, toggleIntensity } = useMapFilters();

  const { events, isLoading } = useEventFeed({
    context: mode,
    zoom,
    bbox,
    ...(mode === 'sector' && sector ? { sector } : {}),
  });

  const { scoreMarkers } = useScoreOverlay(profileActive, events);

  // ── Time-mode state (PLAN-F-021) ────────────────────────────────────────────

  const {
    state: timeModeState,
    setTimeMode,
    setDateRange,
    setPlaybackSpeed,
  } = useTimeModeState();

  const { timeMode, dateRange, playbackSpeed } = timeModeState;

  // Historical events — REST fetch, disabled in live mode.
  const { events: historicalEvents, isLoading: historicalLoading } =
    useHistoricalEvents({
      dateRange: dateRange ?? { from_date: '', to_date: '' },
      enabled: timeMode !== 'live' && dateRange !== null,
    });

  // Playback engine wrapping historical events.
  const playback = usePlayback(historicalEvents, playbackSpeed);

  // Derive the active event set based on time mode.
  const activeEvents: EventPulse[] =
    timeMode === 'live'
      ? events
      : timeMode === 'playback'
        ? playback.visibleEvents
        : historicalEvents;

  // When transitioning to live mode, reconnect WebSocket.
  const prevTimeModeRef = useRef(timeMode);
  useEffect(() => {
    if (prevTimeModeRef.current !== 'live' && timeMode === 'live') {
      // Trigger WebSocket reconnection by clearing + resetting the subscription.
      // The existing useEventFeed effect will re-subscribe on next render.
      // A future iteration will call websocketManager.reconnect() explicitly.
    }
    prevTimeModeRef.current = timeMode;
  }, [timeMode]);

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

      const [west, south, east, north] = currentBbox.split(',').map(Number) as [number, number, number, number];
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

  // Dispatch worker when activeEvents, zoom, or bbox change.
  useEffect(() => {
    dispatchWorker(activeEvents, zoom, bbox);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeEvents, zoom, bbox, dispatchWorker]);

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
          style: env.mapStyleUrl,
          zoom: 2,
          center: [0, 20],
          attributionControl: false,
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
      popupRef.current?.remove();
      popupRootRef.current?.unmount();
      popupRef.current = null;
      popupRootRef.current = null;
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
    async (event: EventPulse) => {
      // Phase 2b subscribers (Progressive Disclosure) receive the event too.
      onExpandEvent?.(event);

      const map = mapRef.current;
      if (!map) return;

      // Tear down any prior popup before opening a new one.
      popupRef.current?.remove();
      popupRootRef.current?.unmount();
      popupRef.current = null;
      popupRootRef.current = null;

      let maplibre: typeof import('maplibre-gl');
      try {
        maplibre = await import('maplibre-gl');
      } catch {
        return; // jsdom / no-maplibre environment — skip popup, navigation still wired via tests
      }
      const container = document.createElement('div');
      container.className = 'stokai-event-popup-root';

      const root = createRoot(container);
      root.render(
        <EventPopup
          event={event}
          onViewDetails={(id) => {
            popupRef.current?.remove();
            popupRootRef.current?.unmount();
            popupRef.current = null;
            popupRootRef.current = null;
            navigate(`/events/${id}/deep-dive`);
          }}
        />,
      );

      const maplibreAny = maplibre as unknown as {
        default?: { Popup: new (opts: unknown) => { setLngLat: (c: [number, number]) => unknown; setDOMContent: (n: HTMLElement) => unknown; addTo: (m: unknown) => unknown; remove: () => void } };
        Popup: new (opts: unknown) => { setLngLat: (c: [number, number]) => unknown; setDOMContent: (n: HTMLElement) => unknown; addTo: (m: unknown) => unknown; remove: () => void };
      };
      const PopupCtor = maplibreAny.default?.Popup ?? maplibreAny.Popup;
      const popup = new PopupCtor({
        closeButton: true,
        closeOnClick: true,
        maxWidth: 'none',
        className: 'stokai-event-popup',
      }) as { setLngLat: (c: [number, number]) => unknown; setDOMContent: (n: HTMLElement) => unknown; addTo: (m: unknown) => unknown; remove: () => void };
      popup.setLngLat([event.lon, event.lat]);
      popup.setDOMContent(container);
      popup.addTo(map);

      popupRef.current = popup;
      popupRootRef.current = root;
    },
    [onExpandEvent, navigate],
  );

  // ── Derived state ───────────────────────────────────────────────────────────

  // Events visible after client-side filters.
  const filteredEvents = individualEvents.filter((e) => {
    const categoryMatch = e.category.some((c) => filters.categories.includes(c));
    const intensityMatch = filters.intensities.includes(e.intensity);
    return categoryMatch && intensityMatch;
  });

  const combinedLoading = isLoading || historicalLoading;
  const showEmptyState = activeEvents.length === 0 && !combinedLoading;

  // Derive empty state message based on time mode.
  const emptyMessage =
    timeMode === 'live'
      ? generateEmptyStateMessage(mode, filters, events.length)
      : generateTimeModeEmptyStateMessage(
          timeMode,
          dateRange,
          activeEvents.length,
          playback.isComplete,
        );

  // ── Side panel content (shared between inline and drawer) ────────────────────

  const sidePanelContent = (
    <div
      data-testid="map-side-panel"
      role="complementary"
      aria-label="Map side panel"
      className="flex h-full flex-col overflow-y-auto"
    >
      <FilterPanel
        filters={filters}
        onToggleCategory={toggleCategory}
        onToggleIntensity={toggleIntensity}
      />
    </div>
  );

  return (
    <div
      data-testid="intelligence-map-root"
      className="relative flex h-[calc(100vh-3rem)] w-full flex-row overflow-hidden"
    >
      {/* MapLibre canvas container — flex-1 min-w-0 so it fills remaining space
          and never overflows its flex parent at any breakpoint (PLAN-N-014 risk note) */}
      <div
        ref={containerRef}
        data-testid="map-container"
        className="relative h-full min-w-0 flex-1"
      >
        {/* Overlays — rendered once map is ready */}
        {mapReady && mapRef.current && (
          <>
            <PulseLayer
              map={mapRef.current}
              events={filteredEvents}
              activeFilters={filters}
              onPulseClick={handlePulseClick}
            />
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            <ClusterLayer
              map={mapRef.current}
              clusters={clusters as any}
              onClusterClick={handleClusterClick as (cluster: unknown) => void}
            />
            {scoreMarkers.length > 0 && (
              <ScoreOverlay map={mapRef.current} markers={scoreMarkers} />
            )}
          </>
        )}

        {/* Context mode switcher stays on the map canvas */}
        <MapContextSwitcher
          mode={mode}
          sector={sector}
          onSetMode={setMode}
          onSetSector={setSector}
        />

        {/* Time mode toolbar — Live / Historical / Playback toggle (PLAN-F-021) */}
        <TimeModeToolbar
          timeMode={timeMode}
          dateRange={dateRange}
          onSetTimeMode={setTimeMode}
          onSetDateRange={(range: DateRange | null) => setDateRange(range)}
        />

        {/* Playback controls — visible only in Playback mode (PLAN-F-021) */}
        {timeMode === 'playback' && (
          <PlaybackControls
            isPlaying={playback.isPlaying}
            isComplete={playback.isComplete}
            speed={playbackSpeed}
            visibleCount={playback.visibleEvents.length}
            totalCount={historicalEvents.length}
            onPlay={playback.play}
            onPause={playback.pause}
            onReset={playback.reset}
            onSetSpeed={setPlaybackSpeed}
          />
        )}

        {/* Empty / quiet state */}
        {showEmptyState && <EmptyState message={emptyMessage} />}

        {/* Loading indicator */}
        {combinedLoading && (
          <div
            data-testid="map-loading"
            className="absolute left-1/2 top-2.5 z-[1000] -translate-x-1/2 rounded-md bg-surface-2/80 px-4 py-1 text-xs text-text"
          >
            Loading events…
          </div>
        )}

        {/* Floating drawer toggle — only visible at mobile (< md) */}
        {isMobile && (
          <button
            data-testid="drawer-toggle-button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open map panels"
            className="fixed bottom-4 right-4 z-[900] min-h-11 rounded-3xl bg-surface-2/90 px-4 py-2.5 text-sm font-semibold text-text hover:bg-surface-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
          >
            Filters
          </button>
        )}
      </div>

      {/* Side panel — inline at md/lg/xl, hidden from flex row at sm */}
      {!isMobile && (
        <div
          className={[
            "h-full shrink-0 overflow-y-auto border-l border-subtle bg-surface-1",
            breakpoint === "lg" || breakpoint === "xl" ? "w-[360px]" : "w-[280px]",
          ].join(" ")}
        >
          {sidePanelContent}
        </div>
      )}

      {/* Drawer — only rendered at sm; contains side panel content */}
      {isMobile && (
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          side="right"
        >
          {sidePanelContent}
        </Drawer>
      )}
    </div>
  );
};

export default IntelligenceMap;
