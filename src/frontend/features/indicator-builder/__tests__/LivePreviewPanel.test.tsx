import { describe, it, expect, vi, beforeEach } from 'vitest';
/**
 * Tests for LivePreviewPanel component.
 *
 * Verifies:
 * - Renders loading spinner while preview is in-flight
 * - Renders scores table once data arrives
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { LivePreviewPanel } from "../LivePreviewPanel";

// Mock useLivePreview
vi.mock("../hooks/useLivePreview", () => ({
  useLivePreview: vi.fn(),
}));
import { useLivePreview as _useLivePreview } from '../hooks/useLivePreview';
const useLivePreview = vi.mocked(_useLivePreview);


describe("LivePreviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading spinner while preview is in-flight", () => {
    useLivePreview.mockReturnValue({
      previews: [],
      isLoading: true,
      error: null,
    });

    render(<LivePreviewPanel formula="revenue * 0.5" />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Computing scores...")).toBeInTheDocument();
  });

  it("renders scores table once data arrives", () => {
    useLivePreview.mockReturnValue({
      previews: [
        { company_id: "c1", company_name: "Corp A", raw_value: 100.0, score: 75.0, geo_adjusted: 70.0 },
        { company_id: "c2", company_name: "Corp B", raw_value: 200.0, score: 85.0, geo_adjusted: null },
        { company_id: "c3", company_name: "Corp C", raw_value: 150.0, score: 60.0, geo_adjusted: 55.0 },
        { company_id: "c4", company_name: "Corp D", raw_value: 50.0,  score: 30.0, geo_adjusted: null },
        { company_id: "c5", company_name: "Corp E", raw_value: 300.0, score: 95.0, geo_adjusted: 90.0 },
      ],
      isLoading: false,
      error: null,
    });

    render(<LivePreviewPanel formula="revenue * 0.5" />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Corp A")).toBeInTheDocument();
    expect(screen.getByText("Corp E")).toBeInTheDocument();
    // Scores rendered
    expect(screen.getByText("75.0")).toBeInTheDocument();
    expect(screen.getByText("95.0")).toBeInTheDocument();
  });

  it("shows empty message when formula is empty", () => {
    useLivePreview.mockReturnValue({
      previews: [],
      isLoading: false,
      error: null,
    });

    render(<LivePreviewPanel formula="" />);

    expect(screen.getByText(/enter a formula/i)).toBeInTheDocument();
  });

  it("shows error when preview fails", () => {
    useLivePreview.mockReturnValue({
      previews: [],
      isLoading: false,
      error: "Preview request failed: HTTP 500",
    });

    render(<LivePreviewPanel formula="revenue" />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByText("Preview request failed: HTTP 500")
    ).toBeInTheDocument();
  });
});
