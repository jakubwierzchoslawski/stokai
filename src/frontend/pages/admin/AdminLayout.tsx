/**
 * AdminLayout.tsx — Desktop-first responsive layout for the Admin Panel.
 *
 * Breakpoint behaviour (PLAN-N-014 TASK-006):
 *   lg (≥1280px):  left navigation rail + main content in a flex row.
 *                  All four admin sections visible and scrollable within <main>.
 *                  No horizontal scroll on <main>.
 *   md (768–1279px): navigation rail collapses to icon-only mode with tooltips.
 *   sm (<768px):   navigation rail hidden; top <header> with hamburger opens <Drawer>.
 *
 * Data tables within admin sections must use overflow-x-auto within their own
 * container (not page-level horizontal scroll).
 *
 * PLAN-N-014 TASK-006
 */

import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import { Drawer } from "@/features/shared/layout/Drawer";
import { useBreakpoint } from "@/features/shared/hooks/useBreakpoint";

// ── Navigation items ──────────────────────────────────────────────────────────

interface NavItem {
  id: string;
  label: string;
  icon: string; // emoji/icon character for icon-only mode
  href: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "sources", label: "Source Management", icon: "S", href: "/admin/sources" },
  { id: "ai-audit", label: "AI Audit Console", icon: "A", href: "/admin/ai-audit" },
  { id: "system", label: "System Operations", icon: "O", href: "/admin/system" },
  { id: "users", label: "User Management", icon: "U", href: "/admin/users" },
];

// ── Props ─────────────────────────────────────────────────────────────────────

export interface AdminLayoutProps {
  children?: React.ReactNode;
  /** Active nav item id for highlighting */
  activeSection?: string;
  /** Navigation callback — called instead of window.location for router integration */
  onNavigate?: (href: string) => void;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function NavRail({
  iconOnly,
  activeSection,
  onNavigate,
}: {
  iconOnly: boolean;
  activeSection?: string;
  onNavigate?: (href: string) => void;
}): React.ReactElement {
  return (
    <nav
      role="navigation"
      aria-label="Admin navigation"
      data-testid="admin-nav-rail"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        padding: iconOnly ? "16px 8px" : "16px",
        background: "#0d1b2a",
        width: iconOnly ? 56 : 220,
        flexShrink: 0,
        minHeight: "100%",
      }}
    >
      <div
        style={{
          fontSize: iconOnly ? 12 : 11,
          fontWeight: 700,
          color: "#8aa3bc",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          padding: "0 0 12px 0",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          marginBottom: 8,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {iconOnly ? "A" : "Admin"}
      </div>

      {NAV_ITEMS.map((item) => {
        const isActive = activeSection === item.id;
        return (
          <button
            key={item.id}
            data-testid={`nav-item-${item.id}`}
            aria-label={item.label}
            title={iconOnly ? item.label : undefined}
            onClick={() => onNavigate?.(item.href)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: iconOnly ? 0 : 10,
              padding: iconOnly ? "10px 0" : "10px 12px",
              justifyContent: iconOnly ? "center" : "flex-start",
              background: isActive ? "rgba(26,115,232,0.15)" : "transparent",
              color: isActive ? "#1a73e8" : "#c5d1dc",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 14,
              fontWeight: isActive ? 600 : 400,
              minHeight: 44,
              width: "100%",
              textAlign: "left",
            }}
          >
            <span
              style={{
                width: 24,
                height: 24,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                fontSize: 14,
                fontWeight: 700,
              }}
            >
              {item.icon}
            </span>
            {!iconOnly && (
              <span
                style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
              >
                {item.label}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

// ── AdminLayout ───────────────────────────────────────────────────────────────

export function AdminLayout({
  children,
  activeSection,
  onNavigate,
}: AdminLayoutProps): React.ReactElement {
  const breakpoint = useBreakpoint();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const isMobile = breakpoint === "sm"; // < 768px — hamburger menu
  const isTablet = breakpoint === "md"; // 768–1279px — icon-only rail

  return (
    <div
      data-testid="admin-layout"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        background: "#f4f6f8",
      }}
    >
      {/* Mobile top header with hamburger */}
      {isMobile && (
        <header
          data-testid="admin-mobile-header"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "0 16px",
            height: 56,
            background: "#0d1b2a",
            flexShrink: 0,
          }}
        >
          <button
            data-testid="admin-hamburger"
            aria-label="Open navigation menu"
            onClick={() => setDrawerOpen(true)}
            style={{
              background: "transparent",
              border: "none",
              color: "#ffffff",
              cursor: "pointer",
              fontSize: 20,
              minHeight: 44,
              minWidth: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            &#9776;
          </button>
          <span style={{ color: "#ffffff", fontWeight: 700, fontSize: 16 }}>Admin</span>
        </header>
      )}

      {/* Main content row */}
      <div
        style={{
          display: "flex",
          flex: 1,
          overflow: "hidden",
        }}
      >
        {/* Left nav rail — visible at md and lg/xl */}
        {!isMobile && (
          <NavRail
            iconOnly={isTablet}
            activeSection={activeSection}
            onNavigate={onNavigate}
          />
        )}

        {/* Main content area */}
        <main
          data-testid="admin-main"
          role="main"
          style={{
            flex: 1,
            minWidth: 0,
            overflowY: "auto",
            overflowX: "hidden", // prevent page-level horizontal scroll
            padding: "24px",
          }}
        >
          {children ?? <Outlet />}
        </main>
      </div>

      {/* Mobile nav drawer */}
      {isMobile && (
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          side="left"
        >
          <NavRail
            iconOnly={false}
            activeSection={activeSection}
            onNavigate={(href) => {
              setDrawerOpen(false);
              onNavigate?.(href);
            }}
          />
        </Drawer>
      )}
    </div>
  );
}

export default AdminLayout;
