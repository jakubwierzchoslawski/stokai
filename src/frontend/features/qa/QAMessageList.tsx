/**
 * QAMessageList â€” scrollable list of Q&A conversation messages.
 *
 * PLAN-F-027 TASK-006
 *
 * Renders a scrollable thread of QAMessageBubble components.
 * Auto-scrolls to the bottom when new messages arrive.
 */
import React, { useEffect, useRef } from "react";
import type { QAAnswer } from "./qaApi";
import { QAMessageBubble } from "./QAMessageBubble";

export interface QAMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer?: QAAnswer | null;
}

export interface QAMessageListProps {
  messages: QAMessage[];
}

export const QAMessageList: React.FC<QAMessageListProps> = ({ messages }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Auto-scroll to bottom when messages change
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="qa-message-list" data-testid="qa-message-list">
      {messages.map((msg) => (
        <QAMessageBubble
          key={msg.id}
          role={msg.role}
          content={msg.content}
          answer={msg.answer}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
};
