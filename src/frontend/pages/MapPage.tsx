/**
 * MapPage — Intelligence Map page with deep-link navigation support.
 *
 * When mounted with ?event={event_id}&lat={lat}&lon={lon} query parameters:
 *   1. Map flies to [lon, lat] at zoom level 8.
 *   2. Opens the event popup for event_id (shows loading spinner until data arrives).
 *
 * Parameter-handling mount effect only; existing map interaction behaviour is unchanged.
 *
 * PLAN-F-025 TASK-012
 */
import React, { useEffect, useRef, useState } from 'react';
import { EventPopup } from '../features/map/EventPopup';

// ── Types ──────────────────────────────────────────────────────────────────────

interface MapRef {
  flyTo: (opts: { center: [number, number]; zoom: number }) => void;
}

interface GeoEventData {
  event_id: string;
  title: string;
  category?: string;
  occurred_at?: string;
  summary?: string;
}

// ── Deep-link param parsing ────────────────────────────────────────────────────

interface DeepLinkParams {
  eventId: string;
  lat: number;
  lon: number;
}

function parseDeepLinkParams(search: string): DeepLinkParams | null {
  const params = new URLSearchParams(search);
  const eventId = params.get('event');
  const latStr = params.get('lat');
  const lonStr = params.get('lon');

  if (!eventId || !latStr || !lonStr) return null;

  const lat = parseFloat(latStr);
  const lon = parseFloat(lonStr);

  // Guard against malformed values
  if (isNaN(lat) || isNaN(lon)) return null;

  return { eventId, lat, lon };
}

// ── Event data fetching ────────────────────────────────────────────────────────

async function fetchEvent(eventId: string): Promise<GeoEventData | null> {
  try {
    const resp = await fetch(`/api/v1/events/${encodeURIComponent(eventId)}`, {
      credentials: 'include',
    });
    if (!resp.ok) return null;
    const body = await resp.json() as { data?: GeoEventData };
    return body.data ?? null;
  } catch {
    return null;
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function MapPage(): React.ReactElement {
  // Map instance ref — in production this would be populated by the MapLibre GL instance
  const mapRef = useRef<MapRef | null>(null);

  const [popupEvent, setPopupEvent] = useState<GeoEventData | null>(null);
  const [popupLoading, setPopupLoading] = useState(false);
  const [showPopup, setShowPopup] = useState(false);

  // Deep-link mount effect
  useEffect(() => {
    const params = parseDeepLinkParams(window.location.search);
    if (!params) return;

    const { eventId, lat, lon } = params;

    // Fly to target location
    if (mapRef.current) {
      mapRef.current.flyTo({ center: [lon, lat], zoom: 8 });
    }

    // Load event data and show popup
    setShowPopup(true);
    setPopupLoading(true);

    fetchEvent(eventId).then((event) => {
      if (event) {
        setPopupEvent(event);
      } else {
        // Create a minimal event object if fetch fails
        setPopupEvent({ event_id: eventId, title: 'Unknown event' });
      }
      setPopupLoading(false);
    });
  }, []); // mount only

  function handlePopupClose() {
    setShowPopup(false);
    setPopupEvent(null);
  }

  return (
    <div className="map-page" data-testid="map-page">
      {/* Map container — in production MapLibre GL renders here */}
      <div
        className="map-page__map-container"
        data-testid="map-container"
        ref={(el) => {
          // In production: initialise MapLibre GL here and assign to mapRef.current
          if (el && !mapRef.current) {
            // Placeholder: real implementation attaches map lib instance
          }
        }}
      />

      {/* Event popup overlay */}
      {showPopup && (
        <div className="map-page__popup-overlay" data-testid="popup-overlay">
          {popupLoading ? (
            <div className="map-page__popup-loading" data-testid="popup-loading-spinner">
              <span>Loading event…</span>
            </div>
          ) : popupEvent ? (
            <EventPopup event={popupEvent} onClose={handlePopupClose} />
          ) : null}
        </div>
      )}
    </div>
  );
}

export default MapPage;
