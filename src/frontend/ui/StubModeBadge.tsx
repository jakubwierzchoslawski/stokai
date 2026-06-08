import * as React from "react";
import { Link } from "react-router-dom";

import {
  type IntegrationKey,
  useIntegrations,
} from "@/lib/api/integrations";

export interface StubModeBadgeProps {
  watch: IntegrationKey[];
  className?: string;
}

export function StubModeBadge({ watch, className }: StubModeBadgeProps) {
  const [open, setOpen] = React.useState(false);
  const { data, isLoading } = useIntegrations();

  if (isLoading || !data) return null;

  const stubbed = watch.filter((k) => data[k]?.mode === "stub");
  if (stubbed.length === 0) return null;

  const reasons = stubbed
    .map((k) => `${k}: ${data[k]?.reason ?? "stub mode"}`)
    .join(" · ");

  return (
    <div
      data-testid="stub-mode-badge"
      className={[
        "select-none cursor-pointer rounded-md border border-subtle bg-surface-2/90 px-3 py-1.5",
        "text-xs text-muted backdrop-blur",
        className ?? "",
      ].join(" ")}
      onClick={() => setOpen((v) => !v)}
      role="button"
      aria-expanded={open}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setOpen((v) => !v);
        }
      }}
    >
      <span className="font-medium">Stub mode:</span> {stubbed.join(", ")}
      {open && (
        <div
          data-testid="stub-mode-badge-popover"
          className="mt-2 max-w-xs whitespace-normal rounded-md border border-default bg-surface-1 p-2 text-xs"
        >
          <div className="text-text">{reasons}</div>
          <Link
            to="/admin/system"
            className="mt-1 inline-block text-signal underline"
          >
            Configure in admin →
          </Link>
        </div>
      )}
    </div>
  );
}
