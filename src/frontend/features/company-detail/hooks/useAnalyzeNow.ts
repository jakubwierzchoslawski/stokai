/**
 * useAnalyzeNow — hook for triggering on-demand AI analysis.
 *
 * Flow:
 *   1. POST /api/v1/companies/{companyId}/analysis → {data: {run_id}}
 *   2. Store run_id
 *   3. Open WebSocket ws[s]://host/ws/analysis/{run_id}
 *   4. On {type: "COMPLETED"} message → call onReportReady(run_id), isLoading=false
 *   5. 409 → set error without entering loading state
 *   6. Cleanup WebSocket on unmount
 *
 * PLAN-F-023 TASK-006
 */
import { useState, useRef, useCallback, useEffect } from 'react';

export interface UseAnalyzeNowOptions {
  companyId: string;
  onReportReady?: (runId: string) => void;
}

export interface UseAnalyzeNowResult {
  trigger: () => Promise<void>;
  isLoading: boolean;
  runId: string | null;
  error: string | null;
}

interface AnalysisResponse {
  data: {
    run_id: string;
    company_id: string;
    status: string;
  };
  meta: Record<string, unknown>;
  error: string | null;
}

function buildWsUrl(runId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/analysis/${runId}`;
}

export function useAnalyzeNow({
  companyId,
  onReportReady,
}: UseAnalyzeNowOptions): UseAnalyzeNowResult {
  const [isLoading, setIsLoading] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  const subscribeToWebSocket = useCallback(
    (newRunId: string) => {
      // Close existing socket if any
      if (wsRef.current) {
        wsRef.current.close();
      }

      const ws = new WebSocket(buildWsUrl(newRunId));
      wsRef.current = ws;

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as { type?: string };
          if (msg.type === 'COMPLETED') {
            setIsLoading(false);
            if (onReportReady) {
              onReportReady(newRunId);
            }
            ws.close();
            wsRef.current = null;
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onerror = () => {
        setError('WebSocket error during analysis.');
        setIsLoading(false);
      };
    },
    [onReportReady],
  );

  const trigger = useCallback(async (): Promise<void> => {
    setError(null);

    const resp = await fetch(`/api/v1/companies/${companyId}/analysis`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });

    if (resp.status === 409) {
      setError('Analysis already in progress for this company.');
      // Do not set isLoading=true on 409
      return;
    }

    if (!resp.ok) {
      setError(`Failed to trigger analysis: ${resp.status}`);
      return;
    }

    setIsLoading(true);

    const body = (await resp.json()) as AnalysisResponse;
    const newRunId = body.data.run_id;
    setRunId(newRunId);

    subscribeToWebSocket(newRunId);
  }, [companyId, subscribeToWebSocket]);

  return { trigger, isLoading, runId, error };
}
