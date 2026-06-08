/**
 * ActiveEventsPanel — lists active geo-events affecting the company.
 *
 * Clicking an event row navigates to /?eventId={event_id} (map view).
 *
 * PLAN-F-023 TASK-005
 */
import React from 'react';
import type { ActiveEventSummary } from './types';

export interface ActiveEventsPanelProps {
  events: ActiveEventSummary[];
  onNavigate?: (url: string) => void;
}

function intensityLabel(intensity: number): string {
  if (intensity >= 8) return 'High';
  if (intensity >= 5) return 'Medium';
  return 'Low';
}

export function ActiveEventsPanel({ events, onNavigate }: ActiveEventsPanelProps): React.ReactElement {
  function handleEventClick(eventId: string) {
    const url = `/?eventId=${encodeURIComponent(eventId)}`;
    if (onNavigate) {
      onNavigate(url);
    } else {
      window.location.href = url;
    }
  }

  return (
    <div className="active-events-panel" data-testid="active-events-panel">
      <h3 className="active-events-panel__title">Active Geo-Events</h3>
      {events.length === 0 ? (
        <p data-testid="active-events-empty">No active geo-events.</p>
      ) : (
        <ul className="active-events-panel__list">
          {events.map((event) => (
            <li
              key={event.event_id}
              className="active-events-panel__item"
              data-testid={`event-item-${event.event_id}`}
            >
              <button
                className="active-events-panel__event-btn"
                onClick={() => handleEventClick(event.event_id)}
                aria-label={`View event: ${event.title}`}
                data-testid={`event-btn-${event.event_id}`}
              >
                <span className="active-events-panel__event-title">{event.title}</span>
                <span
                  className={`active-events-panel__intensity active-events-panel__intensity--${intensityLabel(event.intensity).toLowerCase()}`}
                  aria-label={`Intensity: ${intensityLabel(event.intensity)}`}
                >
                  {intensityLabel(event.intensity)}
                </span>
                <span className="active-events-panel__categories">
                  {event.category.join(', ')}
                </span>
                <span className="active-events-panel__exposure">
                  Exposure: {(event.exposure_magnitude * 100).toFixed(0)}%
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
