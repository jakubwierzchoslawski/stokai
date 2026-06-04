/**
 * useQASession — TanStack Query hook for Q&A session lifecycle.
 *
 * PLAN-F-027 TASK-006
 *
 * Provides:
 *   createSession — creates a new Q&A session via POST /api/v1/qa/sessions
 *   sessionId     — UUID of the active session (or null if not created yet)
 *   isCreating    — true while the create mutation is in flight
 *   error         — error from the last mutation
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createQASession } from "../../api/qaApi";
import type { CreateSessionResponse } from "../../api/qaApi";

export interface UseQASessionReturn {
  sessionId: string | null;
  createSession: () => Promise<string>;
  isCreating: boolean;
  error: Error | null;
}

/**
 * Hook for creating and managing Q&A sessions.
 *
 * Usage:
 *   const { sessionId, createSession, isCreating } = useQASession();
 *   const sid = await createSession();
 */
export function useQASession(): UseQASessionReturn {
  const queryClient = useQueryClient();

  const mutation = useMutation<CreateSessionResponse, Error, void>({
    mutationFn: createQASession,
    onSuccess: (data) => {
      // Cache the session ID for reuse
      queryClient.setQueryData(["qa-session-id"], data.session_id);
    },
  });

  // Retrieve cached session_id if mutation hasn't run yet
  const cachedSessionId =
    queryClient.getQueryData<string>(["qa-session-id"]) ?? null;
  const sessionId = mutation.data?.session_id ?? cachedSessionId;

  const createSession = async (): Promise<string> => {
    const result = await mutation.mutateAsync();
    return result.session_id;
  };

  return {
    sessionId,
    createSession,
    isCreating: mutation.isPending,
    error: mutation.error,
  };
}
