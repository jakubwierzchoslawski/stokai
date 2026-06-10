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
import { api } from '@/lib/api/client';

async function submitFeedback(
  briefId: string,
  payload: FeedbackRequest,
): Promise<FeedbackResponse> {
  return api<FeedbackResponse>('/briefs/' + briefId + '/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function useFeedback(briefId: string) {
  return useMutation({
    mutationFn: (payload: FeedbackRequest) => submitFeedback(briefId, payload),
    onError: (error: Error) => {
      console.warn('[useFeedback] Feedback submission failed:', error.message);
    },
  });
}
