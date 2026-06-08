import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LogOut, Search } from "lucide-react";
import { Button } from "@/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/ui/avatar";
import { useAuth } from "@/app/providers/AuthProvider";
import { ROUTES } from "@/app/routes";
import { ThemeToggle } from "./ThemeToggle";

const PRIMARY_NAV: ReadonlyArray<{ to: string; label: string }> = [
  { to: ROUTES.home, label: "Map" },
  { to: ROUTES.briefs, label: "Briefs" },
  { to: ROUTES.screener, label: "Screener" },
  { to: ROUTES.portfolio, label: "Portfolio" },
  { to: ROUTES.alerts, label: "Alerts" },
  { to: ROUTES.qa, label: "Q&A" },
];

export function TopNav({ onOpenCommand }: { onOpenCommand: () => void }) {
  const { state, logout } = useAuth();
  const nav = useNavigate();
  const user = state.status === "authenticated" ? state.user : null;
  const initials = user?.username?.[0]?.toUpperCase() ?? "?";

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-4 border-b border-border bg-surface-1 px-6">
      <NavLink to={ROUTES.home} className="text-sm font-semibold tracking-tight">
        StokAI
      </NavLink>
      <nav aria-label="Primary" className="hidden md:flex items-center gap-1">
        {PRIMARY_NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `rounded px-2 py-1 text-sm ${isActive ? "bg-surface-2 text-text" : "text-muted hover:text-text"}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onOpenCommand} aria-label="Open command palette" className="gap-2">
          <Search className="h-4 w-4" /><span className="hidden sm:inline text-xs">⌘K</span>
        </Button>
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="User menu">
              <Avatar className="h-7 w-7"><AvatarFallback>{initials}</AvatarFallback></Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[180px]">
            <DropdownMenuItem className="text-xs text-muted">{user?.email ?? "Guest"}</DropdownMenuItem>
            <DropdownMenuSeparator />
            {user?.role === "admin" && (
              <DropdownMenuItem onClick={() => nav(ROUTES.adminHil)}>
                Admin
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => void logout()}>
              <LogOut className="mr-2 h-4 w-4" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
