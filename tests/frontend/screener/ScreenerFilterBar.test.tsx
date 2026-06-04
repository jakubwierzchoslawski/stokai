/**
 * Unit tests for ScreenerFilterBar component (TDD).
 *
 * Covers:
 * - empty state shows "Add filter" button
 * - clicking "Add filter" appends a filter row
 * - second filter row shows AND/OR selector; first row does not
 * - removing a filter row removes it from state
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScreenerFilterBar } from "../../../src/frontend/features/screener/ScreenerFilterBar";

describe("ScreenerFilterBar", () => {
  describe("empty state", () => {
    it("shows 'Add filter' button in empty state", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      expect(screen.getByLabelText("Add filter")).toBeInTheDocument();
    });

    it("shows no filter rows initially", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      expect(screen.queryByTestId("filter-row-0")).not.toBeInTheDocument();
    });
  });

  describe("adding filters", () => {
    it("appends a filter row when 'Add filter' is clicked", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      fireEvent.click(screen.getByLabelText("Add filter"));
      expect(screen.getByTestId("filter-row-0")).toBeInTheDocument();
    });

    it("appends a second filter row on second click", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      fireEvent.click(screen.getByLabelText("Add filter"));
      fireEvent.click(screen.getByLabelText("Add filter"));
      expect(screen.getByTestId("filter-row-0")).toBeInTheDocument();
      expect(screen.getByTestId("filter-row-1")).toBeInTheDocument();
    });
  });

  describe("AND/OR selector visibility", () => {
    it("does NOT show AND/OR selector for the first filter row", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      fireEvent.click(screen.getByLabelText("Add filter"));
      // First row (idx=0) should not have logical op selector
      expect(
        screen.queryByLabelText("Logical operator for filter 1"),
      ).not.toBeInTheDocument();
    });

    it("shows AND/OR selector for the second filter row", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      fireEvent.click(screen.getByLabelText("Add filter"));
      fireEvent.click(screen.getByLabelText("Add filter"));
      // Second row (idx=1) should have logical op selector
      expect(
        screen.getByLabelText("Logical operator for filter 2"),
      ).toBeInTheDocument();
    });
  });

  describe("removing filters", () => {
    it("removes the filter row when Remove is clicked", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      fireEvent.click(screen.getByLabelText("Add filter"));
      // Row 0 is visible
      expect(screen.getByTestId("filter-row-0")).toBeInTheDocument();
      // Remove it
      fireEvent.click(screen.getByLabelText("Remove filter 1"));
      expect(screen.queryByTestId("filter-row-0")).not.toBeInTheDocument();
    });

    it("removes only the targeted row when multiple filters exist", () => {
      render(<ScreenerFilterBar onApply={jest.fn()} />);
      fireEvent.click(screen.getByLabelText("Add filter"));
      fireEvent.click(screen.getByLabelText("Add filter"));
      // Remove first row
      fireEvent.click(screen.getByLabelText("Remove filter 1"));
      // One row should remain
      expect(screen.queryByTestId("filter-row-0")).toBeInTheDocument();
      expect(screen.queryByTestId("filter-row-1")).not.toBeInTheDocument();
    });
  });

  describe("apply filters", () => {
    it("calls onApply with current filters when Apply is clicked", () => {
      const onApply = jest.fn();
      render(<ScreenerFilterBar onApply={onApply} />);
      fireEvent.click(screen.getByLabelText("Add filter"));
      fireEvent.click(screen.getByLabelText("Apply filters"));
      expect(onApply).toHaveBeenCalledTimes(1);
      expect(onApply).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({ column: expect.any(String) }),
        ]),
      );
    });
  });
});
