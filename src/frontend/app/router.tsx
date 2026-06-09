import React, { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RequireAuth } from "./guards/RequireAuth";
import { RequireAdmin } from "./guards/RequireAdmin";
import { OnboardingGate } from "./guards/OnboardingGate";
import { AppShell } from "@/layout/AppShell";
import { ComingSoon } from "@/ui/ComingSoon";
import { NotFound } from "@/ui/NotFound";
import { ROUTES } from "./routes";

const IntelligenceMapPage = lazy(() =>
  import("@/features/intelligence-map/IntelligenceMapPage").then((m) => ({ default: m.IntelligenceMapPage }))
);
const BriefsPage = lazy(() =>
  import("@/features/briefs/BriefsPage").then((m) => ({ default: m.BriefsPage }))
);
const BriefDetailPage = lazy(() =>
  import("@/features/briefs/BriefDetailPage").then((m) => ({ default: m.BriefDetailPage }))
);
const ScreenerPage = lazy(() =>
  import("@/features/screener/ScreenerPage").then((m) => ({ default: m.ScreenerPage }))
);
const CompanyDetailPage = lazy(() =>
  import("@/features/company-detail/CompanyDetailPage").then((m) => ({ default: m.CompanyDetailPage }))
);
const AlertsCenterPage = lazy(() =>
  import("@/pages/AlertsCenterPage").then((m) => ({ default: m.AlertsCenterPage }))
);
const QAChatPanel = lazy(() =>
  import("@/features/qa/QAChatPanel").then((m) => ({ default: m.QAChatPanel }))
);
const OnboardingFlow = lazy(() =>
  import("@/features/onboarding/OnboardingFlow").then((m) => ({ default: m.OnboardingFlow }))
);
const AdminLayout = lazy(() =>
  import("@/pages/admin/AdminLayout").then((m) => ({ default: m.AdminLayout }))
);
const HilQueue = lazy(() =>
  import("@/pages/admin/hil/HilQueue").then((m) => ({ default: m.HilQueue }))
);
const SourcesPage = lazy(() =>
  import("@/pages/admin/sources/SourcesPage").then((m) => ({ default: m.SourcesPage }))
);
const AiAuditConsolePage = lazy(() =>
  import("@/pages/admin/ai-audit/AiAuditConsolePage").then((m) => ({ default: m.AiAuditConsolePage }))
);
const IngestionJobsTab = lazy(() =>
  import("@/pages/admin/system/IngestionJobsTab").then((m) => ({ default: m.IngestionJobsTab }))
);

function Loader() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-signal border-t-transparent" />
    </div>
  );
}

function S({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Loader />}>{children}</Suspense>;
}

export function AppRouter() {
  return (
    <Routes>
      {/* Public */}
      <Route path={ROUTES.login} element={<LoginPage />} />
      <Route path={ROUTES.register} element={<RegisterPage />} />

      {/* Onboarding — auth-required but outside the OnboardingGate redirect */}
      <Route
        path={ROUTES.onboarding}
        element={
          <RequireAuth>
            <S><OnboardingFlow /></S>
          </RequireAuth>
        }
      />

      {/* Protected: RequireAuth → OnboardingGate (outlet) → AppShell (outlet) → pages */}
      <Route element={<RequireAuth><OnboardingGate /></RequireAuth>}>
        <Route element={<AppShell />}>
          <Route path={ROUTES.home} element={<S><IntelligenceMapPage /></S>} />
          <Route path={ROUTES.briefs} element={<S><BriefsPage /></S>} />
          <Route path={ROUTES.brief} element={<S><BriefDetailPage /></S>} />
          <Route path={ROUTES.screener} element={<S><ScreenerPage /></S>} />
          <Route path={ROUTES.company} element={<S><CompanyDetailPage /></S>} />
          <Route path={ROUTES.portfolio} element={<ComingSoon feature="Portfolio" />} />
          <Route path={ROUTES.watchlist} element={<ComingSoon feature="Watchlist" />} />
          <Route path={ROUTES.alerts} element={<S><AlertsCenterPage /></S>} />
          <Route path={ROUTES.qa} element={<S><QAChatPanel /></S>} />
          <Route path={ROUTES.events} element={<ComingSoon feature="Event Deep-Dive" />} />

          {/* Admin — additional RequireAdmin guard */}
          <Route element={<RequireAdmin><AdminLayout /></RequireAdmin>}>
            <Route path={ROUTES.adminHil} element={<S><HilQueue /></S>} />
            <Route path={ROUTES.adminSources} element={<S><SourcesPage /></S>} />
            <Route path={ROUTES.adminAudit} element={<S><AiAuditConsolePage /></S>} />
            <Route path={ROUTES.adminSystem} element={<S><IngestionJobsTab /></S>} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
