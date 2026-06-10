/**
 * useAnalyzeNow — hook for triggering on-demand AI analysis.
 *
 * Flow:
 *   1. POST /companies/{companyId}/analysis → {run_id, company_id, status}
 *   2. Store run_id
 *   3. Open WebSocket via apiSocket('/ws/analysis/{run_id}')
 *   4. On {type: "COMPLETED"} message → call onReportReady(run_id), isLoading=false
 *   5. 409 → set error without entering loading state
 *   6. 5-minute safety timeout: backend WebSocket handler not yet wired (Phase 4)
 *   7. Cleanup on unmount
 *
 * PLAN-F-023 TASK-006
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import { api } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';
import { apiSocket } from '@/lib/api/ws';
import type { SocketHandle } from '@/lib/api/ws';

const ANALYSIS_TIMEOUT_MS = 5 * 60 * 1000;

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

interface AnalysisRunResponse {
  run_id: string;
  company_id: string;
  status: string;
}

export function useAnalyzeNow({
  companyId,
  onReportReady,
}: UseAnalyzeNowOptions): UseAnalyzeNowResult {
  const [isLoading, setIsLoading] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<SocketHandle | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanup = useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const subscribeToWebSocket = useCallback(
    (newRunId: string) => {
      cleanup();

      socketRef.current = apiSocket('/ws/analysis/' + newRunId, {
        onMessage: (msg: unknown) => {
          const typed = msg as { type?: string };
          if (typed.type === 'COMPLETED') {
            setIsLoading(false);
            onReportReady?.(newRunId);
            cleanup();
          }
        },
        onClose: () => {},
        onError: () => {
          setError('WebSocket error during analysis.');
          setIsLoading(false);
          cleanup();
        },
      });

      // Safety timeout: backend producer for /ws/analysis/{run_id} is not yet
      // wired (Phase 4). Without this, the spinner would hang indefinitely.
      timeoutRef.current = setTimeout(() => {
        setError(
          'Analysis timed out. The analysis backend is not yet available; ' +
            'please try again later.',
        );
        setIsLoading(false);
        cleanup();
      }, ANALYSIS_TIMEOUT_MS);
    },
    [onReportReady, cleanup],
  );

  const trigger = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const run = await api<AnalysisRunResponse>(
        '/companies/' + companyId + '/analysis',
        { method: 'POST' },
      );
      setIsLoading(true);
      setRunId(run.run_id);
      subscribeToWebSocket(run.run_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Analysis already in progress for this company.');
        return;
      }
      const msg = err instanceof Error ? err.message : String(err);
      setError('Failed to trigger analysis: ' + msg);
    }
  }, [companyId, subscribeToWebSocket]);

  return { trigger, isLoading, runId, error };
}
