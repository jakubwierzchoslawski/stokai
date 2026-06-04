/**
 * BriefsReaderResponsive.test.tsx — TDD tests for Briefs Reader mobile-first layout.
 *
 * Tests written first (red phase) per PLAN-N-014 TASK-008.
 *
 * The "BriefsReaderPage" corresponds to BriefDetailPage in the existing codebase
 * (route /briefs/:brief_id). Mobile-first constraints are applied to BriefDetailPage.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ── Mock dependencies ─────────────────────────────────────────────────────────

jest.mock("../../../src/frontend/features/briefs/hooks/useBriefDetail", () => ({
  useBriefDetail: jest.fn(),
}));

jest.mock("../../../src/frontend/features/briefs/FeedbackWidget", () => ({
  FeedbackWidget: () => <div data-testid="feedback-widget" />,
}));

jest.mock("../../../src/frontend/features/briefs/SafeHtmlRenderer", () => ({
  SafeHtmlRenderer: ({ html, className }: { html: string; className?: string }) => (
    <div
      data-testid="safe-html-renderer"
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  ),
}));

const { useBriefDetail } = require("../../../src/frontend/features/briefs/hooks/useBriefDetail");

import { BriefDetailPage } from "../../../src/frontend/features/briefs/BriefDetailPage";

// ── Mock data ─────────────────────────────────────────────────────────────────

const longReport = {
  brief_id: "brief-1",
  type: "morning_brief" as const,
  date: "2026-06-04",
  headline: "Morning Brief — 4 June 2026",
  confidence: 0.85,
  sample_size: 12,
  low_sample: false,
  content_html: `
    <p>This is a long paragraph that describes market conditions in detail. It contains extended text
    that would overflow at narrow viewports if not properly constrained with responsive CSS.</p>
    <p>Long URL: https://very-long-domain-name-that-should-not-overflow.example.com/path/to/resource</p>
    <table>
      <thead><tr><th>Col1</th><th>Col2</th><th>Col3</th></tr></thead>
      <tbody><tr><td>data1</td><td>data2</td><td>data3</td></tr></tbody>
    </table>
  `,
};

function renderBriefDetailPage() {
  useBriefDetail.mockReturnValue({
    data: { data: longReport },
    isLoading: false,
    isError: false,
  });

  return render(
    <MemoryRouter initialEntries={["/briefs/brief-1"]}>
      <Routes>
        <Route path="/briefs/:brief_id" element={<BriefDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────name────────────────

describe("BriefDetailPage mobile-first responsive (AC-002)", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("root article element has overflow-x-hidden constraint", () => {
    renderBriefDetailPage();

    const article = screen.getByTestId("brief-detail");
    expect(article.style.overflowX).toBe("hidden");
  });

  it("content body wrapper has max-w-full and overflow-x-hidden", () => {
    renderBriefDetailPage();

    const body = screen.getByTestId("brief-body");
    const style = body.style;
    // Either max-width 100% or overflow-x hidden must be present
    const hasConstraint =
      style.maxWidth === "100%" ||
      style.overflowX === "hidden" ||
      body.className.includes("overflow-x-hidden") ||
      body.className.includes("max-w-full");
    expect(hasConstraint).toBe(true);
  });
});
