import React from "react";
import { NavLink } from "react-router-dom";
import { Map, FileText, Search, Bell } from "lucide-react";
import { ROUTES } from "@/app/routes";

const ITEMS = [
  { to: ROUTES.home, label: "Map", Icon: Map },
  { to: ROUTES.briefs, label: "Briefs", Icon: FileText },
  { to: ROUTES.screener, label: "Screener", Icon: Search },
  { to: ROUTES.alerts, label: "Alerts", Icon: Bell },
] as const;

export function MobileNav() {
  return (
    <nav
      aria-label="Primary mobile"
      className="fixed bottom-0 left-0 right-0 z-30 flex h-14 border-t border-border bg-surface-1 md:hidden"
    >
      {ITEMS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] ${
              isActive ? "text-text" : "text-muted"
            }`
          }
        >
          <Icon className="h-5 w-5" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
