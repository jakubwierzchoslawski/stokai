/**
 * useLivePreview — fetches live score previews for 5 sample companies.
 *
 * - Calls /preview with 500ms debounce.
 * - Returns 5 company preview rows.
 * - Shows loading state during in-flight requests.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

export interface CompanyPreviewRow {
  company_id: string;
  company_name: string;
  raw_value: number | null;
  score: number | null;
  geo_adjusted: number | null;
}

interface UseLivePreviewOptions {
  debounceMs?: number;
}

interface UseLivePreviewReturn {
  previews: CompanyPreviewRow[];
  isLoading: boolean;
  error: string | null;
}

const PREVIEW_URL = "/api/v1/indicators/preview";

async function fetchPreviews(formulaDsl: string): Promise<CompanyPreviewRow[]> {
  const response = await fetch(PREVIEW_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ formula_dsl: formulaDsl }),
  });

  if (!response.ok) {
    throw new Error(`Preview request failed: HTTP ${response.status}`);
  }

  const json = await response.json();
  return json.data.previews as CompanyPreviewRow[];
}

export function useLivePreview(
  formula: string,
  options: UseLivePreviewOptions = {}
): UseLivePreviewReturn {
  const { debounceMs = 500 } = options;
  const [debouncedFormula, setDebouncedFormula] = useState<string>(formula);
  const [error, setError] = useState<string | null>(null);

  // Debounce the formula
  useEffect(() => {
    if (!formula.trim()) {
      setDebouncedFormula("");
      return;
    }
    const timer = setTimeout(() => {
      setDebouncedFormula(formula);
    }, debounceMs);
    return () => clearTimeout(timer);
  }, [formula, debounceMs]);

  const queryClient = useQueryClient();

  const { data, isFetching } = useQuery<CompanyPreviewRow[], Error>({
    queryKey: ["live-preview", debouncedFormula],
    queryFn: () => fetchPreviews(debouncedFormula),
    enabled: debouncedFormula.trim().length > 0,
    staleTime: 30_000, // 30 seconds
    retry: 1,
  });

  return {
    previews: data ?? [],
    isLoading: isFetching,
    error: error,
  };
}
