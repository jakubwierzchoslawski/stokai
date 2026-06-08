import React from "react";
import { Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Toaster } from "@/ui/sonner";
import { Button } from "@/ui/button";
import { TopNav } from "./TopNav";
import { MobileNav } from "./MobileNav";
import { CommandPalette, useCommandPalette } from "./CommandPalette";

async function pingHealth(): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 3_000);
  try {
    const res = await fetch("/health", { signal: ctrl.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export function AppShell() {
  const { open, setOpen } = useCommandPalette();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: pingHealth,
    refetchInterval: 30_000,
    retry: 0,
  });

  if (health.isSuccess && !health.data) {
    return <BackendUnreachable onRetry={() => health.refetch()} />;
  }

  return (
    <div className="min-h-screen bg-surface-0 text-text">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-2 focus:z-50 focus:rounded focus:bg-surface-2 focus:px-3 focus:py-1.5 focus:text-sm"
      >
        Skip to content
      </a>
      <TopNav onOpenCommand={() => setOpen(true)} />
      <main id="main" className="pb-16 md:pb-0">
        <Outlet />
      </main>
      <MobileNav />
      <CommandPalette open={open} onOpenChange={setOpen} />
      <Toaster richColors closeButton position="bottom-right" />
    </div>
  );
}

function BackendUnreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 p-6 text-text">
      <div className="max-w-md rounded-lg border border-border bg-surface-1 p-6 text-center">
        <h1 className="text-xl font-semibold">Backend unreachable</h1>
        <p className="mt-2 text-sm text-muted">
          The API is not responding at <code>/health</code>. Confirm <code>docker compose up</code> is running.
        </p>
        <Button className="mt-4" onClick={onRetry}>Retry</Button>
      </div>
    </div>
  );
}
