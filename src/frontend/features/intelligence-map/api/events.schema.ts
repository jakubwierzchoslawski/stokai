import { z } from "zod";

export const EventPulseSchema = z.object({
  event_id: z.string(),
  category: z.array(z.string()),
  intensity: z
    .number()
    .int()
    .min(1)
    .max(5)
    .transform((n) => n as 1 | 2 | 3 | 4 | 5),
  headline: z.string(),
  timestamp: z.string(),
  lat: z.number(),
  lon: z.number(),
  relevance_window_end: z.string(),
  affected_companies: z.array(
    z.object({
      company_id: z.string(),
      ticker: z.string(),
      score_delta: z.number(),
    }),
  ),
});

export const EventsArraySchema = z.array(EventPulseSchema);

export type EventPulseFromSchema = z.infer<typeof EventPulseSchema>;
