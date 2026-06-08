/**
 * qaApi â€” typed API client for Q&A chat endpoints.
 *
 * PLAN-F-027 TASK-006
 *
 * Endpoints:
 *   POST /api/v1/qa/sessions              â€” create a new Q&A session
 *   POST /api/v1/qa/sessions/{id}/messages â€” submit question (SSE stream)
 */

export interface QASource {
  type: string;
  id: string;
  description: string;
}

export interface QAAnswer {
  answer_text: string;
  sources: QASource[];
  confidence: number;
  cost_usd: number;
  cost_limited: boolean;
}

export interface CreateSessionResponse {
  session_id: string;
}

export interface SSEChunkEvent {
  type: "chunk";
  text: string;
}

export interface SSEDoneEvent {
  type: "done";
  answer: QAAnswer;
}

export interface SSECostLimitedEvent {
  type: "cost_limited";
  partial_answer: QAAnswer;
}

export type SSEEvent = SSEChunkEvent | SSEDoneEvent | SSECostLimitedEvent;

/**
 * Create a new Q&A session for the current user.
 *
 * @returns Promise<CreateSessionResponse> with session_id
 */
export async function createQASession(): Promise<CreateSessionResponse> {
  const response = await fetch("/api/v1/qa/sessions", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      `Failed to create Q&A session: ${response.status} ${error?.detail || response.statusText}`,
    );
  }
  return response.json();
}

/**
 * Submit a question to a Q&A session and stream the response.
 *
 * Returns an EventSource-compatible object. Callers should listen to the
 * 'message' event and parse each SSEEvent from data.
 *
 * @param sessionId - UUID of the Q&A session
 * @param question  - The user's question text
 * @returns EventSource configured to stream the Q&A response
 */
export function submitQAQuestion(
  sessionId: string,
  question: string,
): { eventSource: EventSource; abort: () => void } {
  // We use fetch with a ReadableStream for POST + SSE. EventSource only supports GET.
  // The caller (useQAStream) handles the streaming via fetch + ReadableStream.
  // This factory method is kept for testability.
  throw new Error(
    "Use useQAStream hook which handles POST + SSE streaming via fetch API.",
  );
}

/**
 * Submit a question via fetch and return the Response for SSE streaming.
 * Use this in useQAStream for POST-based SSE.
 */
export async function submitQuestionFetch(
  sessionId: string,
  question: string,
): Promise<Response> {
  return fetch(`/api/v1/qa/sessions/${sessionId}/messages`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}
