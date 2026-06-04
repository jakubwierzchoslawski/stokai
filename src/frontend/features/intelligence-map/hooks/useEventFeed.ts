/**
 * useEventFeed.ts — TanStack Query hook for event data + WebSocket merge.
 *
 * Fetches the initial event list via GET /api/v1/events on mount. Maintains
 * a local EventPulse[] state that is extended by WebSocket pushes on the
 * ws/events channel. Unsubscribes on unmount.
 *
 * PLAN-F-019 TASK-002
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { fetchEvents, type EventsQueryParams } from '../api/events.api';
import type { EventPulse } from '../types/map.types';

// ── WebSocket subscription manager ───────────────────────────────────────────
// Lightweight inline manager that connects to ws/events and dispatches messages.
// Replaced by the shared WebSocketManager utility when that module is available.

export interface WsSubscription {
  unsubscribe: () => void;
}

export type OnEventCallback = (event: EventPulse) => void;

/** Subscribe to the ws/events channel. Returns an unsubscribe handle. */
export function subscribeToEventChannel(
  onEvent: OnEventCallback,
): WsSubscription {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/events`;

  let socket: WebSocket | null = null;
  let closed = false;

  function connect() {
    if (closed) return;
    socket = new WebSocket(wsUrl);

    socket.addEventListener('message', (msg) => {
      try {
        const parsed: unknown = JSON.parse(msg.data as string);
        onEvent(parsed as EventPulse);
      } catch {
        // Malformed messages are silently dropped — they must not crash the component.
      }
    });

    socket.addEventListener('error', () => {
      // Errors are swallowed; reconnection can be added in a future iteration.
    });
  }

  connect();

  return {
    unsubscribe() {
      closed = true;
      socket?.close();
      socket = null;
    },
  };
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseEventFeedParams {
  context?: 'global' | 'portfolio' | 'sector';
  zoom?: number;
  bbox?: string;
}

export interface UseEventFeedResult {
  events: EventPulse[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

export function useEventFeed(
  params: UseEventFeedParams = {},
): UseEventFeedResult {
  const { context = 'global', zoom, bbox } = params;

  // TanStack Query — initial fetch.  Key changes trigger a re-fetch.
  const queryResult = useQuery<EventPulse[], Error>({
    queryKey: ['events', { context, zoom, bbox }],
    queryFn: () =>
      fetchEvents({ context, zoom, bbox } as EventsQueryParams),
  });

  // Local state merges query data + WebSocket pushes.
  const [wsEvents, setWsEvents] = useState<EventPulse[]>([]);
  const subscriptionRef = useRef<WsSubscription | null>(null);

  // Reset WebSocket-accumulated events when the query key changes so stale
  // pushes from a previous context/bbox do not pollute the new view.
  const prevContextRef = useRef<string>('');
  const currentKey = `${context}|${zoom}|${bbox}`;
  if (prevContextRef.current !== currentKey) {
    prevContextRef.current = currentKey;
    setWsEvents([]);
  }

  useEffect(() => {
    const sub = subscribeToEventChannel((incoming: EventPulse) => {
      // Validate the minimum required fields before accepting the push.
      if (
        typeof incoming?.event_id === 'string' &&
        typeof incoming?.lat === 'number' &&
        typeof incoming?.lon === 'number'
      ) {
        setWsEvents((prev) => [...prev, incoming]);
      }
    });
    subscriptionRef.current = sub;
    return () => {
      sub.unsubscribe();
      subscriptionRef.current = null;
    };
  }, [context, zoom, bbox]);

  const baseEvents = queryResult.data ?? [];
  const events = [...baseEvents, ...wsEvents];

  return {
    events,
    isLoading: queryResult.isLoading,
    isError: queryResult.isError,
    error: queryResult.error,
  };
}
