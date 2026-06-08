import { useQuery } from "@tanstack/react-query";

import {
  fetchIntegrations,
  type Integrations,
} from "@/features/system/integrationsApi";

export type IntegrationKey = string;
export type { Integrations } from "@/features/system/integrationsApi";

export interface UseIntegrationsResult {
  data: Integrations | undefined;
  isLoading: boolean;
  isError: boolean;
  isStub: (key: IntegrationKey) => boolean;
}

export function useIntegrations(): UseIntegrationsResult {
  const q = useQuery<Integrations>({
    queryKey: ["system", "integrations"],
    queryFn: fetchIntegrations,
    staleTime: 5 * 60 * 1000,
  });

  return {
    data: q.data,
    isLoading: q.isLoading,
    isError: q.isError,
    isStub: (key) => q.data?.[key]?.mode === "stub",
  };
}
