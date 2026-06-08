import { z } from "zod";
import { api } from "@/lib/api/client";

const IntegrationSchema = z.object({
  provider: z.string(),
  mode: z.enum(["live", "stub", "missing"]),
  reason: z.string().optional(),
});

export const IntegrationsSchema = z.record(z.string(), IntegrationSchema);
export type Integrations = z.infer<typeof IntegrationsSchema>;

export async function fetchIntegrations(): Promise<Integrations> {
  const raw = await api<unknown>("/system/integrations");
  return IntegrationsSchema.parse(raw);
}
