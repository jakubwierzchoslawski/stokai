import { useQuery } from "@tanstack/react-query";

import { fetchEvents } from "../api/events.api";
import type { EventPulse } from "../types/map.types";
import type { DateRange } from "../types/time-mode.types";

const EMPTY: EventPulse[] = [];

export interface HistoricalEventsParams {
  dateRange: DateRange;
  enabled: boolean;
}

export interface UseHistoricalEventsResult {
  events: EventPulse[];
  isLoading: boolean;
  isError: boolean;
}

export function useHistoricalEvents(
  params: HistoricalEventsParams,
): UseHistoricalEventsResult {
  const { dateRange, enabled } = params;

  const q = useQuery<EventPulse[], Error>({
    queryKey: ["historical-events", dateRange.from_date, dateRange.to_date],
    queryFn: async () => {
      const data = await fetchEvents({
        from: dateRange.from_date,
        to: dateRange.to_date,
      });
      return [...data].sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      );
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  if (!enabled) return { events: EMPTY, isLoading: false, isError: false };

  return {
    events: q.data ?? EMPTY,
    isLoading: q.isLoading,
    isError: q.isError,
  };
}
