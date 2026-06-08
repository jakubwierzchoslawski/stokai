import React from "react";

interface ComingSoonProps {
  feature?: string;
}

export function ComingSoon({ feature }: ComingSoonProps) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="text-4xl">🚧</div>
      <h1 className="text-2xl font-semibold text-text">{feature ?? "Coming Soon"}</h1>
      <p className="text-muted">This feature is under active development.</p>
    </div>
  );
}
