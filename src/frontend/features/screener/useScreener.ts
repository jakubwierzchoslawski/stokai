/**
 * useScreener — TanStack Query infinite query hook for the Company Screener.
 *
 * Wraps POST /api/v1/screener with useInfiniteQuery.
 *
 * Cache configuration (REQ-N-015):
 *   staleTime: 60_000 ms (1 minute)
 *   gcTime:   300_000 ms (5 minutes)
 *
 * The queryKey includes the full serialised request (filters, sort, event_id)
 * so that different filter combinations are cached independently.
 *
 * getNextPageParam extracts next_cursor from the last page response.
 */
import {
  useInfiniteQuery,
  type InfiniteData,
  type QueryKey,
} from "@tanstack/react-query";
import type {
  ApiEnvelope,
  ScreenerRequest,
  ScreenerResponse,
} from "./screenerTypes";

const SCREENER_ENDPOINT = "/api/v1/screener";

async function fetchScreenerPage(
  request: ScreenerRequest,
  cursor?: string,
): Promise<ScreenerResponse> {
  const body: ScreenerRequest = { ...request };
  if (cursor) {
    body.cursor = cursor;
  } else {
    delete body.cursor;
  }

  const resp = await fetch(SCREENER_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    throw new Error(`Screener request failed: ${resp.status}`);
  }

  const envelope: ApiEnvelope<ScreenerResponse> = await resp.json();
  if (envelope.error) {
    throw new Error(envelope.error);
  }
  return envelope.data;
}

/** Stable query key for a given ScreenerRequest (cursor excluded — it varies per page). */
export function screenerQueryKey(request: ScreenerRequest): QueryKey {
  // Omit cursor from key so all pages share the same cache entry group.
  const { cursor: _cursor, ...requestWithoutCursor } = request;
  return ["screener", requestWithoutCursor] as const;
}

export function useScreener(request: ScreenerRequest) {
  return useInfiniteQuery<
    ScreenerResponse,
    Error,
    InfiniteData<ScreenerResponse>,
    QueryKey,
    string | undefined
  >({
    queryKey: screenerQueryKey(request),
    queryFn: ({ pageParam }) => fetchScreenerPage(request, pageParam),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    staleTime: 60_000,
    gcTime: 300_000,
  });
}
