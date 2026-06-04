/**
 * Tests for QAMessageBubble, QASourcesList, QACostLimitNotice, QAChatPanel.
 *
 * PLAN-F-027 TASK-006
 *
 * Tests:
 *   - QAMessageBubble renders confidence score (AC-002)
 *   - QAMessageBubble renders sources list (AC-002)
 *   - QAMessageBubble shows cost_limit notice when cost_limited=true (AC-003)
 *   - QAMessageBubble hides cost_limit notice when cost_limited=false (AC-003)
 *   - QAChatPanel submits question on Enter key
 *   - QASourcesList is collapsed by default and expands on click
 */
// jsdom does not implement scrollIntoView — mock it globally for all tests
window.HTMLElement.prototype.scrollIntoView = jest.fn();

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QAMessageBubble } from "../../../src/frontend/components/qa/QAMessageBubble";
import { QASourcesList } from "../../../src/frontend/components/qa/QASourcesList";
import { QAChatPanel } from "../../../src/frontend/components/qa/QAChatPanel";

// ── Mock hooks ─────────────────────────────────────────────────────────────────

jest.mock("../../../src/frontend/components/qa/useQASession", () => ({
  useQASession: jest.fn(() => ({
    sessionId: "test-session-id",
    createSession: jest.fn().mockResolvedValue("test-session-id"),
    isCreating: false,
    error: null,
  })),
}));

const mockStreamAnswer = jest.fn().mockResolvedValue(undefined);

jest.mock("../../../src/frontend/components/qa/useQAStream", () => ({
  useQAStream: jest.fn(() => ({
    streamAnswer: mockStreamAnswer,
    streamingText: "",
    isStreaming: false,
    answer: null,
    error: null,
    reset: jest.fn(),
  })),
}));

// ── TanStack Query mock ────────────────────────────────────────────────────────

jest.mock("@tanstack/react-query", () => ({
  useMutation: jest.fn(() => ({
    mutateAsync: jest.fn().mockResolvedValue({ session_id: "test-session-id" }),
    isPending: false,
    error: null,
    data: { session_id: "test-session-id" },
  })),
  useQueryClient: jest.fn(() => ({
    setQueryData: jest.fn(),
    getQueryData: jest.fn(() => "test-session-id"),
  })),
}));

// ── Fixtures ───────────────────────────────────────────────────────────────────

const baseSources = [
  { type: "event", id: "evt-1", description: "AAPL Q1 2026 earnings release" },
  { type: "filing", id: "fil-2", description: "AAPL 10-K 2025 annual report" },
];

const baseAnswer = {
  answer_text: "Your AAPL exposure is 15% of portfolio.",
  sources: baseSources,
  confidence: 0.87,
  cost_usd: 0.12,
  cost_limited: false,
};

// ── QAMessageBubble tests ──────────────────────────────────────────────────────

describe("QAMessageBubble", () => {
  describe("confidence score", () => {
    it("renders confidence as percentage badge for assistant messages", () => {
      render(
        <QAMessageBubble
          role="assistant"
          content={baseAnswer.answer_text}
          answer={baseAnswer}
        />,
      );
      const badge = screen.getByTestId("qa-confidence-badge");
      expect(badge).toBeInTheDocument();
      expect(badge.textContent).toContain("87%");
    });

    it("does not render confidence badge for user messages", () => {
      render(<QAMessageBubble role="user" content="What is my AAPL exposure?" />);
      expect(screen.queryByTestId("qa-confidence-badge")).not.toBeInTheDocument();
    });

    it("rounds confidence to nearest percent", () => {
      const answer = { ...baseAnswer, confidence: 0.873 };
      render(
        <QAMessageBubble role="assistant" content="Test" answer={answer} />,
      );
      const badge = screen.getByTestId("qa-confidence-badge");
      expect(badge.textContent).toContain("87%");
    });
  });

  describe("sources list", () => {
    it("renders QASourcesList when sources are present", () => {
      render(
        <QAMessageBubble
          role="assistant"
          content={baseAnswer.answer_text}
          answer={baseAnswer}
        />,
      );
      expect(screen.getByTestId("qa-sources-list")).toBeInTheDocument();
    });

    it("does not render sources list when sources are empty", () => {
      const answerNoSources = { ...baseAnswer, sources: [] };
      render(
        <QAMessageBubble
          role="assistant"
          content="Test"
          answer={answerNoSources}
        />,
      );
      expect(screen.queryByTestId("qa-sources-list")).not.toBeInTheDocument();
    });
  });

  describe("cost limit notice", () => {
    it("shows cost limit notice when cost_limited=true", () => {
      const limitedAnswer = { ...baseAnswer, cost_limited: true };
      render(
        <QAMessageBubble
          role="assistant"
          content="Partial answer"
          answer={limitedAnswer}
        />,
      );
      expect(screen.getByTestId("qa-cost-limit-notice")).toBeInTheDocument();
      expect(screen.getByTestId("qa-cost-limit-notice").textContent).toContain(
        "Cost limit reached",
      );
    });

    it("hides cost limit notice when cost_limited=false", () => {
      render(
        <QAMessageBubble
          role="assistant"
          content="Full answer"
          answer={baseAnswer}
        />,
      );
      expect(
        screen.queryByTestId("qa-cost-limit-notice"),
      ).not.toBeInTheDocument();
    });

    it("does not render cost limit notice for user messages", () => {
      render(<QAMessageBubble role="user" content="Question text" />);
      expect(
        screen.queryByTestId("qa-cost-limit-notice"),
      ).not.toBeInTheDocument();
    });
  });
});

// ── QASourcesList tests ────────────────────────────────────────────────────────

describe("QASourcesList", () => {
  it("is collapsed by default", () => {
    render(<QASourcesList sources={baseSources} />);
    expect(screen.queryByTestId("qa-sources-content")).not.toBeInTheDocument();
    const toggle = screen.getByTestId("qa-sources-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("expands when toggle is clicked", () => {
    render(<QASourcesList sources={baseSources} />);
    const toggle = screen.getByTestId("qa-sources-toggle");

    fireEvent.click(toggle);

    expect(screen.getByTestId("qa-sources-content")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("collapses again when toggle clicked a second time", () => {
    render(<QASourcesList sources={baseSources} />);
    const toggle = screen.getByTestId("qa-sources-toggle");

    fireEvent.click(toggle); // open
    fireEvent.click(toggle); // close

    expect(screen.queryByTestId("qa-sources-content")).not.toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("renders all source descriptions when expanded", () => {
    render(<QASourcesList sources={baseSources} />);
    fireEvent.click(screen.getByTestId("qa-sources-toggle"));

    expect(screen.getByText("AAPL Q1 2026 earnings release")).toBeInTheDocument();
    expect(screen.getByText("AAPL 10-K 2025 annual report")).toBeInTheDocument();
  });

  it("returns null when sources list is empty", () => {
    const { container } = render(<QASourcesList sources={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

// ── QAChatPanel tests ──────────────────────────────────────────────────────────

describe("QAChatPanel", () => {
  beforeEach(() => {
    mockStreamAnswer.mockClear();
  });

  it("renders the chat input and submit button", () => {
    render(<QAChatPanel initialSessionId="test-session-id" />);
    expect(screen.getByTestId("qa-chat-input")).toBeInTheDocument();
    expect(screen.getByTestId("qa-chat-submit")).toBeInTheDocument();
  });

  it("submits question on Enter keypress", async () => {
    render(<QAChatPanel initialSessionId="test-session-id" />);
    const input = screen.getByTestId("qa-chat-input");

    fireEvent.change(input, { target: { value: "What is my AAPL exposure?" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    // useQAStream.streamAnswer should have been called
    expect(mockStreamAnswer).toHaveBeenCalledTimes(1);
    expect(mockStreamAnswer).toHaveBeenCalledWith(
      "test-session-id",
      "What is my AAPL exposure?",
    );
  });

  it("does not submit on Shift+Enter (newline mode)", async () => {
    render(<QAChatPanel initialSessionId="test-session-id" />);
    const input = screen.getByTestId("qa-chat-input");

    fireEvent.change(input, { target: { value: "Multi-line question" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", shiftKey: true });

    expect(mockStreamAnswer).not.toHaveBeenCalled();
  });

  it("does not submit empty input", async () => {
    render(<QAChatPanel initialSessionId="test-session-id" />);
    const input = screen.getByTestId("qa-chat-input");

    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    expect(mockStreamAnswer).not.toHaveBeenCalled();
  });
});
