import { z } from "zod";

import { api } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

import { EventsArraySchema } from "./events.schema";
import type { EventPulse } from "../types/map.types";

export interface EventsQueryParams {
  /** "west,south,east,north" */
  bbox?: string;
  zoom?: number;
  context?: "global" | "portfolio" | "sector";
  sector?: string;
  /** ISO 8601 — historical mode start */
  from?: string;
  /** ISO 8601 — historical mode end */
  to?: string;
}

function buildQuery(params: EventsQueryParams): string {
  const usp = new URLSearchParams();
  if (params.bbox !== undefined) usp.set("bbox", params.bbox);
  if (params.zoom !== undefined) usp.set("zoom", String(params.zoom));
  if (params.context !== undefined) usp.set("context", params.context);
  if (params.sector !== undefined) usp.set("sector", params.sector);
  if (params.from !== undefined) usp.set("from", params.from);
  if (params.to !== undefined) usp.set("to", params.to);
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchEvents(
  params: EventsQueryParams,
): Promise<EventPulse[]> {
  const raw = await api<unknown>(`/events${buildQuery(params)}`);
  try {
    return EventsArraySchema.parse(raw) as EventPulse[];
  } catch (err) {
    if (err instanceof z.ZodError) {
      throw new ApiError(
        0,
        "CONTRACT_MISMATCH",
        "Events response failed schema validation",
        { issues: err.issues },
      );
    }
    throw err;
  }
}
