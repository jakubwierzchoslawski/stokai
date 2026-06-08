import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/ui/command";
import { ROUTES } from "@/app/routes";

const NAV: ReadonlyArray<{ label: string; path: string; group: string }> = [
  { label: "Intelligence Map", path: ROUTES.home, group: "Navigate" },
  { label: "Briefs", path: ROUTES.briefs, group: "Navigate" },
  { label: "Screener", path: ROUTES.screener, group: "Navigate" },
  { label: "Portfolio", path: ROUTES.portfolio, group: "Navigate" },
  { label: "Watchlist", path: ROUTES.watchlist, group: "Navigate" },
  { label: "Alerts", path: ROUTES.alerts, group: "Navigate" },
  { label: "Q&A", path: ROUTES.qa, group: "Navigate" },
  { label: "Admin: HIL Queue", path: ROUTES.adminHil, group: "Admin" },
  { label: "Admin: Data Sources", path: ROUTES.adminSources, group: "Admin" },
  { label: "Admin: System Operations", path: ROUTES.adminSystem, group: "Admin" },
  { label: "Admin: AI Audit", path: ROUTES.adminAudit, group: "Admin" },
];

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const nav = useNavigate();
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Type a command or search…" />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        {["Navigate", "Admin"].map((g) => (
          <CommandGroup key={g} heading={g}>
            {NAV.filter((n) => n.group === g).map((n) => (
              <CommandItem key={n.path} onSelect={() => { nav(n.path); onOpenChange(false); }}>
                {n.label}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return { open, setOpen };
}
