import * as React from "react";

import type { EventPulse } from "../types/map.types";

export interface EventPopupProps {
  event: EventPulse;
  onViewDetails: (eventId: string) => void;
}

const INTENSITY_VAR: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: "var(--positive)",
  2: "var(--pulse-low)",
  3: "var(--pulse-mid)",
  4: "var(--pulse-high)",
  5: "var(--pulse-extreme)",
};

export function EventPopup({ event, onViewDetails }: EventPopupProps) {
  return (
    <div
      data-testid="event-popup"
      className="flex w-64 flex-col gap-2 rounded-md bg-surface-1 p-3 text-text"
    >
      <div className="flex items-start gap-2">
        <span
          aria-label={`intensity ${event.intensity}`}
          className="mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full"
          style={{ background: INTENSITY_VAR[event.intensity] }}
        />
        <div className="text-base font-medium leading-tight">
          {event.headline}
        </div>
      </div>
      <div className="text-xs text-muted">
        Intensity {event.intensity} · {event.affected_companies.length} affected
      </div>
      <button
        type="button"
        onClick={() => onViewDetails(event.event_id)}
        className="self-start rounded-md border border-default bg-surface-2 px-2.5 py-1 text-xs font-medium hover:bg-surface-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
      >
        View details →
      </button>
    </div>
  );
}
