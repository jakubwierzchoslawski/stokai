/**
 * QAChatPanel — top-level Q&A chat panel component.
 *
 * PLAN-F-027 TASK-006
 *
 * Renders a scrollable message thread (QAMessageList) and a text-input footer.
 * On Enter keypress (or button click), submits the question via useQAStream.
 * Adds streaming text as a temporary bubble; replaces it with the final answer
 * on 'done' event.
 *
 * useQASession is used to lazily create the session before the first message.
 */
import React, { useState, useCallback, useId, useRef } from "react";
import type { QAMessage } from "./QAMessageList";
import { QAMessageList } from "./QAMessageList";
import { useQASession } from "./useQASession";
import { useQAStream } from "./useQAStream";

/** Monotonic ID counter — avoids crypto.randomUUID dependency in test env */
let _msgCounter = 0;
function newMsgId(): string {
  return `msg-${++_msgCounter}-${Date.now()}`;
}

export interface QAChatPanelProps {
  /** Optional pre-existing session ID. If not provided, a new session is created. */
  initialSessionId?: string;
}

export const QAChatPanel: React.FC<QAChatPanelProps> = ({
  initialSessionId,
}) => {
  const [messages, setMessages] = useState<QAMessage[]>([]);
  const [inputText, setInputText] = useState<string>("");
  const [activeSessionId, setActiveSessionId] = useState<string | null>(
    initialSessionId ?? null,
  );

  const { createSession } = useQASession();
  const { streamAnswer, isStreaming, answer, streamingText, reset } =
    useQAStream();

  const inputId = useId();

  const handleSubmit = useCallback(async () => {
    const question = inputText.trim();
    if (!question || isStreaming) return;

    setInputText("");

    // Add user message immediately
    const userMsgId = newMsgId();
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: question },
    ]);

    // Ensure we have a session
    let sessionId = activeSessionId;
    if (!sessionId) {
      sessionId = await createSession();
      setActiveSessionId(sessionId);
    }

    // Placeholder assistant message while streaming
    const assistantMsgId = newMsgId();
    setMessages((prev) => [
      ...prev,
      { id: assistantMsgId, role: "assistant", content: "" },
    ]);

    // Stream the answer
    await streamAnswer(sessionId, question);
  }, [inputText, isStreaming, activeSessionId, createSession, streamAnswer]);

  // When streaming text arrives, update the placeholder bubble
  React.useEffect(() => {
    if (streamingText) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant") {
          updated[updated.length - 1] = { ...last, content: streamingText };
        }
        return updated;
      });
    }
  }, [streamingText]);

  // When final answer arrives, finalise the last assistant bubble
  React.useEffect(() => {
    if (answer) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant") {
          updated[updated.length - 1] = {
            ...last,
            content: answer.answer_text,
            answer,
          };
        }
        return updated;
      });
      reset();
    }
  }, [answer, reset]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="qa-chat-panel" data-testid="qa-chat-panel">
      <div className="qa-chat-messages">
        <QAMessageList messages={messages} />
      </div>

      <div className="qa-chat-footer">
        <label htmlFor={inputId} className="sr-only">
          Ask a question about your portfolio
        </label>
        <textarea
          id={inputId}
          className="qa-chat-input"
          data-testid="qa-chat-input"
          placeholder="Ask a question about your portfolio..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
          rows={2}
        />
        <button
          className="qa-chat-submit"
          data-testid="qa-chat-submit"
          onClick={handleSubmit}
          disabled={isStreaming || !inputText.trim()}
        >
          {isStreaming ? "Thinking..." : "Ask"}
        </button>
      </div>
    </div>
  );
};
