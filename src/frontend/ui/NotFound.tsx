import React from "react";
import { Link } from "react-router-dom";
import { ROUTES } from "@/app/routes";

export function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="text-6xl font-bold text-muted">404</div>
      <h1 className="text-2xl font-semibold text-text">Page Not Found</h1>
      <p className="text-muted">The page you're looking for doesn't exist.</p>
      <Link to={ROUTES.home} className="text-signal underline">
        Go home
      </Link>
    </div>
  );
}
