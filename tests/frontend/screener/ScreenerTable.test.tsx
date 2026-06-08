import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * Unit tests for ScreenerTable component (TDD).
 *
 * Covers:
 * - renders column headers with correct labels
 * - clicking header calls onSortChange with column + direction
 * - clicking active header again reverses sort direction
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScreenerTable } from "../../../src/frontend/features/screener/ScreenerTable";
import type { ScreenerRow } from "../../../src/frontend/features/screener/screenerTypes";

function makeRow(overrides: Partial<ScreenerRow> = {}): ScreenerRow {
  return {
    company_id: "00000000-0000-0000-0000-000000000001",
    ticker: "AAPL",
    name: "Apple Inc",
    sector: "Technology",
    market_cap: 3_000_000_000,
    custom_score: 87.65,
    score_delta: -3.21,
    current_price: 180.99,
    active_events_count: 2,
    active_event_categories: ["geopolitical", "financial"],
    ...overrides,
  };
}

const DEFAULT_PROPS = {
  rows: [makeRow()],
  sortColumn: "custom_score" as const,
  sortDir: "desc" as const,
  onSortChange: vi.fn(),
  hasNextPage: false,
  isFetchingNextPage: false,
  onLoadMore: vi.fn(),
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("ScreenerTable", () => {
  describe("column headers", () => {
    it("renders all required column header labels", () => {
      render(<ScreenerTable {...DEFAULT_PROPS} />);

      expect(screen.getByText("Ticker")).toBeInTheDocument();
      expect(screen.getByText("Name")).toBeInTheDocument();
      expect(screen.getByText("Sector")).toBeInTheDocument();
      expect(screen.getByText("Market Cap")).toBeInTheDocument();
      expect(screen.getByText("Custom Score")).toBeInTheDocument();
      expect(screen.getByText("Score Delta")).toBeInTheDocument();
      expect(screen.getByText("Price")).toBeInTheDocument();
      expect(screen.getByText("Active Events")).toBeInTheDocument();
    });
  });

  describe("sort interaction", () => {
    it("calls onSortChange with the clicked column and 'desc' when not currently sorted", () => {
      const onSortChange = vi.fn();
      render(
        <ScreenerTable
          {...DEFAULT_PROPS}
          sortColumn="custom_score"
          sortDir="desc"
          onSortChange={onSortChange}
        />,
      );

      // Click a column that is not currently sorted
      fireEvent.click(screen.getByText("Ticker"));

      expect(onSortChange).toHaveBeenCalledWith("ticker", "desc");
    });

    it("calls onSortChange with 'asc' when clicking the active sort column sorted desc", () => {
      const onSortChange = vi.fn();
      render(
        <ScreenerTable
          {...DEFAULT_PROPS}
          sortColumn="custom_score"
          sortDir="desc"
          onSortChange={onSortChange}
        />,
      );

      // Click the active column header â€” should toggle to asc
      fireEvent.click(screen.getByText(/Custom Score/));

      expect(onSortChange).toHaveBeenCalledWith("custom_score", "asc");
    });

    it("calls onSortChange with 'desc' when clicking the active sort column sorted asc", () => {
      const onSortChange = vi.fn();
      render(
        <ScreenerTable
          {...DEFAULT_PROPS}
          sortColumn="name"
          sortDir="asc"
          onSortChange={onSortChange}
        />,
      );

      // Click the active column header â€” should toggle to desc
      fireEvent.click(screen.getByText("Name"));

      expect(onSortChange).toHaveBeenCalledWith("name", "desc");
    });

    it("shows descending sort indicator on active column", () => {
      render(
        <ScreenerTable {...DEFAULT_PROPS} sortColumn="custom_score" sortDir="desc" />,
      );

      // The active header should contain a down arrow indicator
      const header = screen.getByText(/Custom Score/);
      expect(header.textContent).toContain("â†“");
    });

    it("shows ascending sort indicator on active column", () => {
      render(
        <ScreenerTable {...DEFAULT_PROPS} sortColumn="custom_score" sortDir="asc" />,
      );

      const header = screen.getByText(/Custom Score/);
      expect(header.textContent).toContain("â†‘");
    });
  });

  describe("load more", () => {
    it("shows Load more button when hasNextPage is true", () => {
      render(<ScreenerTable {...DEFAULT_PROPS} hasNextPage={true} />);
      expect(screen.getByLabelText("Load more companies")).toBeInTheDocument();
    });

    it("does not show Load more button when hasNextPage is false", () => {
      render(<ScreenerTable {...DEFAULT_PROPS} hasNextPage={false} />);
      expect(screen.queryByLabelText("Load more companies")).not.toBeInTheDocument();
    });

    it("calls onLoadMore when Load more is clicked", () => {
      const onLoadMore = vi.fn();
      render(
        <ScreenerTable {...DEFAULT_PROPS} hasNextPage={true} onLoadMore={onLoadMore} />,
      );
      fireEvent.click(screen.getByLabelText("Load more companies"));
      expect(onLoadMore).toHaveBeenCalledTimes(1);
    });
  });
});
