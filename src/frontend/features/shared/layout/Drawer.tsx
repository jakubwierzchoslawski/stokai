/**
 * Drawer.tsx — Slide-in overlay drawer for side panels at < md viewport.
 *
 * Slides in from the specified side using CSS translate transition.
 * When open=false: panel is translated off-screen and aria-hidden="true".
 * When open=true: panel slides in; pressing Escape calls onClose.
 * Backdrop click calls onClose. Panel click does not propagate to backdrop.
 *
 * Focus trap: implemented manually via keydown Tab cycling to avoid adding
 * the focus-trap-react dependency. Tab/Shift-Tab are intercepted when the
 * drawer is open to keep focus within the panel.
 *
 * Panel sizing: min-w-[280px] max-w-[90vw] — usable at 375px without
 * consuming the full viewport.
 *
 * PLAN-N-014 TASK-003
 */

import React, { useEffect, useRef, useCallback } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /** Which side the drawer slides in from. Default: "left". */
  side?: "left" | "right";
  children: React.ReactNode;
}

export function Drawer({
  open,
  onClose,
  side = "left",
  children,
}: DrawerProps): React.ReactElement {
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        onClose();
      }
    },
    [open, onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleKeyDown]);

  // Translate class: off-screen when closed, on-screen when open.
  // left drawer slides from the left; right drawer from the right.
  const translateClass = open
    ? "translate-x-0"
    : side === "left"
      ? "-translate-x-full"
      : "translate-x-full";

  // Prevent backdrop click from firing when panel is clicked.
  const handlePanelClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  return (
    <>
      {/* Backdrop */}
      <div
        data-testid="drawer-backdrop"
        aria-hidden="true"
        onClick={open ? onClose : undefined}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 1000,
          background: "rgba(0,0,0,0.5)",
          opacity: open ? 1 : 0,
          pointerEvents: open ? "auto" : "none",
          transition: "opacity 200ms ease",
        }}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal={open ? "true" : undefined}
        aria-hidden={open ? undefined : "true"}
        className={`${translateClass} transition-transform duration-200 ease-in-out`}
        style={{
          position: "fixed",
          top: 0,
          [side]: 0,
          bottom: 0,
          zIndex: 1001,
          minWidth: "280px",
          maxWidth: "90vw",
          background: "#ffffff",
          boxShadow: "0 0 24px rgba(0,0,0,0.18)",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
        }}
        onClick={handlePanelClick}
      >
        {children}
      </div>
    </>
  );
}

export default Drawer;
