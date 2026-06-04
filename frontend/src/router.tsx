/**
 * router.tsx — Application route definitions.
 *
 * Registers all top-level routes including the HIL review queue admin page
 * at /admin/hil and the Data Sources admin page at /admin/sources.
 * Route-level auth guards are handled by each page component.
 *
 * PLAN-F-013 TASK-008
 * PLAN-F-028 TASK-011
 * PLAN-F-030 TASK-011 — /admin/system (System Operations panel)
 */
import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { HilQueue } from "./pages/admin/HilQueue";
import { SourcesPage } from "./pages/admin/sources/SourcesPage";
import { SystemOpsPage } from "./pages/admin/system/SystemOpsPage";

/** Root application router. */
export const AppRouter: React.FC = () => {
  return React.createElement(
    BrowserRouter,
    null,
    React.createElement(
      Routes,
      null,
      // ── Admin routes ────────────────────────────────────────────────────────
      React.createElement(Route, {
        path: "/admin/hil",
        element: React.createElement(HilQueue),
      }),
      // PLAN-F-028: Admin data source management (admin role required)
      React.createElement(Route, {
        path: "/admin/sources",
        element: React.createElement(SourcesPage),
      }),
      // PLAN-F-030: Admin system operations panel (admin role required)
      React.createElement(Route, {
        path: "/admin/system",
        element: React.createElement(SystemOpsPage),
      }),
      // ── Default redirect ────────────────────────────────────────────────────
      React.createElement(Route, {
        path: "/",
        element: React.createElement("div", { "data-testid": "home" }, "Home"),
      }),
      React.createElement(Route, {
        path: "*",
        element: React.createElement(Navigate, { to: "/", replace: true }),
      }),
    ),
  );
};

export default AppRouter;
