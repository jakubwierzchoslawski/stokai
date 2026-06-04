/**
 * EventPopup — popup component displayed when a user clicks an event marker
 * on the Intelligence Map.
 *
 * Renders event metadata and a "Show in Screener" button that navigates to
 * /screener?event_id=<event.event_id>, pre-filtering the screener to companies
 * affected by the selected event (AC-003).
 */
import React from "react";
import { useNavigate } from "react-router-dom";

export interface EventPopupProps {
  event: {
    event_id: string;
    title: string;
    category?: string;
    occurred_at?: string;
    summary?: string;
  };
  onClose?: () => void;
}

export function EventPopup({ event, onClose }: EventPopupProps) {
  const navigate = useNavigate();

  function handleShowInScreener() {
    navigate(`/screener?event_id=${encodeURIComponent(event.event_id)}`);
    onClose?.();
  }

  return (
    <div className="event-popup" role="dialog" aria-label={`Event: ${event.title}`}>
      <div className="event-popup__header">
        <h3 className="event-popup__title">{event.title}</h3>
        {onClose && (
          <button
            className="event-popup__close"
            onClick={onClose}
            aria-label="Close event popup"
          >
            &times;
          </button>
        )}
      </div>

      {event.category && (
        <p className="event-popup__category">
          <strong>Category:</strong> {event.category}
        </p>
      )}

      {event.occurred_at && (
        <p className="event-popup__date">
          <strong>Date:</strong> {new Date(event.occurred_at).toLocaleDateString()}
        </p>
      )}

      {event.summary && (
        <p className="event-popup__summary">{event.summary}</p>
      )}

      <div className="event-popup__actions">
        <button
          className="event-popup__screener-btn"
          onClick={handleShowInScreener}
          aria-label={`Show companies affected by ${event.title} in screener`}
        >
          Show in Screener
        </button>
      </div>
    </div>
  );
}

export default EventPopup;
