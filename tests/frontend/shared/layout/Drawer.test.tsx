/**
 * Drawer.test.tsx — TDD tests for the Drawer component.
 *
 * Tests written first (red phase) per PLAN-N-014 TASK-003.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { Drawer } from "../../../../src/frontend/features/shared/layout/Drawer";

describe("Drawer", () => {
  const noop = jest.fn();

  beforeEach(() => {
    noop.mockClear();
  });

  it("has aria-hidden='true' and off-screen class when open=false", () => {
    render(
      <Drawer open={false} onClose={noop}>
        <span>Content</span>
      </Drawer>,
    );
    const panel = screen.getByRole("dialog", { hidden: true });
    expect(panel).toHaveAttribute("aria-hidden", "true");
    // Panel should have translate class indicating it is off-screen
    expect(panel.className).toMatch(/translate/);
  });

  it("is visible (aria-hidden false or absent) when open=true", () => {
    render(
      <Drawer open={true} onClose={noop}>
        <span>Content</span>
      </Drawer>,
    );
    const panel = screen.getByRole("dialog");
    // aria-hidden should not be 'true' when drawer is open
    expect(panel).not.toHaveAttribute("aria-hidden", "true");
  });

  it("calls onClose when Escape key is pressed while open", () => {
    render(
      <Drawer open={true} onClose={noop}>
        <span>Content</span>
      </Drawer>,
    );
    fireEvent.keyDown(document, { key: "Escape", code: "Escape" });
    expect(noop).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked", () => {
    render(
      <Drawer open={true} onClose={noop}>
        <span data-testid="inner-content">Content</span>
      </Drawer>,
    );
    const backdrop = screen.getByTestId("drawer-backdrop");
    fireEvent.click(backdrop);
    expect(noop).toHaveBeenCalledTimes(1);
  });

  it("does NOT call onClose when clicking inside the panel content", () => {
    render(
      <Drawer open={true} onClose={noop}>
        <span data-testid="inner-content">Content</span>
      </Drawer>,
    );
    const inner = screen.getByTestId("inner-content");
    fireEvent.click(inner);
    expect(noop).not.toHaveBeenCalled();
  });

  it("sets aria-hidden to 'true' when transitioning from open=true to open=false", () => {
    const { rerender } = render(
      <Drawer open={true} onClose={noop}>
        <span>Content</span>
      </Drawer>,
    );

    // Initially open — aria-hidden should not be 'true'
    let panel = screen.getByRole("dialog");
    expect(panel).not.toHaveAttribute("aria-hidden", "true");

    // Close the drawer
    rerender(
      <Drawer open={false} onClose={noop}>
        <span>Content</span>
      </Drawer>,
    );

    panel = screen.getByRole("dialog", { hidden: true });
    expect(panel).toHaveAttribute("aria-hidden", "true");
  });
});
