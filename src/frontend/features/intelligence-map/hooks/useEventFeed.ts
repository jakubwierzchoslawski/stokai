import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { apiSocket } from "@/lib/api/ws";

import { fetchEvents, type EventsQueryParams } from "../api/events.api";
import { EventPulseSchema } from "../api/events.schema";
import type { EventPulse } from "../types/map.types";

export interface UseEventFeedParams {
  context?: "global" | "portfolio" | "sector";
  zoom?: number;
  bbox?: string;
  sector?: string;
}

export interface UseEventFeedResult {
  events: EventPulse[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

interface WsFrame {
  type: string;
  event?: unknown;
}

export function useEventFeed(
  params: UseEventFeedParams = {},
): UseEventFeedResult {
  const { context = "global", zoom, bbox, sector } = params;

  const q = useQuery<EventPulse[], Error>({
    queryKey: ["events", { context, zoom, bbox, sector }],
    queryFn: () =>
      fetchEvents({ context, zoom, bbox, sector } as EventsQueryParams),
  });

  const [wsEvents, setWsEvents] = useState<EventPulse[]>([]);

  // Reset WS accumulator when the query key shifts so stale pushes from a
  // previous context/bbox do not pollute the new view.
  const prevKeyRef = useRef("");
  const currentKey = `${context}|${zoom}|${bbox}|${sector ?? ""}`;
  if (prevKeyRef.current !== currentKey) {
    prevKeyRef.current = currentKey;
    if (wsEvents.length > 0) setWsEvents([]);
  }

  useEffect(() => {
    const handle = apiSocket("/api/v1/events/feed", {
      onMessage: (msg) => {
        const frame = msg as WsFrame;
        if (
          frame?.type !== "event.created" &&
          frame?.type !== "event.updated"
        ) {
          return;
        }
        const parsed = EventPulseSchema.safeParse(frame.event);
        if (!parsed.success) return;
        setWsEvents((prev) => [...prev, parsed.data as EventPulse]);
      },
      onClose: () => {
        // apiSocket handles 4401 → refresh → reconnect internally.
      },
    });
    return () => handle.close();
  }, [context, zoom, bbox, sector]);

  const baseEvents = q.data ?? [];
  return {
    events: [...baseEvents, ...wsEvents],
    isLoading: q.isLoading,
    isError: q.isError,
    error: q.error,
  };
}
