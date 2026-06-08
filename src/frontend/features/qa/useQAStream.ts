/**
 * useQAStream â€” EventSource-style hook for streaming Q&A answers.
 *
 * PLAN-F-027 TASK-006
 *
 * Uses fetch + ReadableStream to consume SSE events from a POST endpoint
 * (EventSource only supports GET, so we use fetch directly).
 *
 * Appends text chunks to a local buffer in real time.
 * Finalises the answer on 'done' or 'cost_limited' events.
 *
 * Returns:
 *   streamAnswer  â€” kick off streaming for a question
 *   streamingText â€” partial text assembled from chunk events so far
 *   isStreaming   â€” true while stream is in progress
 *   answer        â€” the final QAAnswer once stream completes
 *   error         â€” error if the stream failed
 */
import { useState, useCallback } from "react";
import type { QAAnswer, SSEEvent } from "./qaApi";
import { submitQuestionFetch } from "./qaApi";

export interface UseQAStreamReturn {
  streamAnswer: (sessionId: string, question: string) => Promise<void>;
  streamingText: string;
  isStreaming: boolean;
  answer: QAAnswer | null;
  error: Error | null;
  reset: () => void;
}

/**
 * Parse a single SSE data line into an SSEEvent.
 *
 * @param line - Raw "data: {...}" line from SSE stream
 * @returns Parsed SSEEvent or null if line is not parseable
 */
function parseSseLine(line: string): SSEEvent | null {
  if (!line.startsWith("data:")) return null;
  const json = line.slice("data:".length).trim();
  try {
    return JSON.parse(json) as SSEEvent;
  } catch {
    return null;
  }
}

export function useQAStream(): UseQAStreamReturn {
  const [streamingText, setStreamingText] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [answer, setAnswer] = useState<QAAnswer | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const reset = useCallback(() => {
    setStreamingText("");
    setIsStreaming(false);
    setAnswer(null);
    setError(null);
  }, []);

  const streamAnswer = useCallback(
    async (sessionId: string, question: string): Promise<void> => {
      reset();
      setIsStreaming(true);

      try {
        const response = await submitQuestionFetch(sessionId, question);

        if (!response.ok) {
          throw new Error(`Stream request failed: ${response.status}`);
        }

        if (!response.body) {
          throw new Error("Response body is null â€” cannot stream");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete lines
          const lines = buffer.split("\n");
          // Keep incomplete last line in buffer
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;

            const event = parseSseLine(trimmed);
            if (!event) continue;

            if (event.type === "chunk") {
              setStreamingText((prev) => prev + event.text);
            } else if (event.type === "done") {
              setAnswer(event.answer);
              setIsStreaming(false);
              return;
            } else if (event.type === "cost_limited") {
              setAnswer(event.partial_answer);
              setIsStreaming(false);
              return;
            }
          }
        }

        // Stream ended without a terminal event
        setIsStreaming(false);
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        setIsStreaming(false);
      }
    },
    [reset],
  );

  return {
    streamAnswer,
    streamingText,
    isStreaming,
    answer,
    error,
    reset,
  };
}
