import React from "react";

export function Sidebar({ children }: { children?: React.ReactNode }) {
  return (
    <aside className="hidden lg:flex w-56 shrink-0 flex-col border-r border-border bg-surface-1">
      {children}
    </aside>
  );
}
