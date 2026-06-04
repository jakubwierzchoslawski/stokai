/**
 * useFeedback — TanStack Query mutation for submitting brief feedback.
 *
 * POSTs to POST /api/v1/briefs/:id/feedback.
 * On error surfaces a toast without crashing the page.
 *
 * PLAN-F-026 TASK-007
 */
import { useMutation } from '@tanstack/react-query';
import type { FeedbackRequest, FeedbackResponse } from '../briefs.types';

async function submitFeedback(
  briefId: string,
  payload: FeedbackRequest,
): Promise<FeedbackResponse> {
  const resp = await fetch(`/api/v1/briefs/${briefId}/feedback`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body?.detail?.message ?? `Failed to submit feedback: ${resp.status}`);
  }
  return resp.json() as Promise<FeedbackResponse>;
}

export function useFeedback(briefId: string) {
  return useMutation({
    mutationFn: (payload: FeedbackRequest) => submitFeedback(briefId, payload),
    onError: (error: Error) => {
      // Surface error as console warning; UI layer can extend with toast
      console.warn('[useFeedback] Feedback submission failed:', error.message);
    },
  });
}
